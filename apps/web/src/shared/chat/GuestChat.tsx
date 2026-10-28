"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { ComponentType } from "react";
import Link from "next/link";
import type { AnswerRendererProps, GuestBriefRendererProps, GuestBriefConfirmationChange, GuestBriefConfirmationLine, GuestTurnResultRendererProps, TurnResultActions, DomainTarget } from "@/composition/registration";
import { formatMediaTime } from "@/shared/chat/media-format";
import {
  canStartRequest,
  claimRequest,
  classifyFailure,
  classifySessionFailure,
  hasUnresolvedRequest,
  isCurrentGeneration,
  releaseRequest,
  resolveAnswerOnlyReceipt,
  retryModeForFailure,
  type RetryMode,
} from "@/shared/chat/chat-state";
import {
  ApiError,
  createGuestSession,
  GuestMessageResponse,
  GuestMediaDescriptor,
  GuestSession,
  GuestBriefReceipt,
  GuestBriefSnapshot,
  GuestBriefConfirmation,
  checkGuestFreshness,
  confirmGuestBriefEdit,
  fetchGuestMedia,
  sendGuestMessage,
} from "@/shared/api/client";
import { copyPlainText, directionForLanguageTag, hasCompleteLabelBundle, labelsForLanguage, normalizeLanguageTag, type CopyResult } from "@/shared/chat/presentation";

type ChatTurn = {
  id: string;
  question: string;
  answer?: GuestMessageResponse;
  error?: string;
  retryMode?: RetryMode;
  sending?: boolean;
  stale?: boolean;
  freshnessError?: string;
  receipt?: GuestBriefReceipt | null;
  appliedDelta?: Record<string, unknown>;
  resumeReceiptId?: string;
  partialSuccess?: boolean;
  recovered?: boolean;
  briefSnapshot?: GuestBriefSnapshot;
  answerOnlyReceiptId?: string;
  briefConfirmation?: GuestBriefConfirmation;
  confirmationDismissed?: boolean;
  confirmationRequestId?: string;
  sameIdOnly?: boolean;
  languageTag?: string;
  scopeSessionId?: string;
};

function requestId() {
  return crypto.randomUUID();
}

function confirmationText(languageTag: string) {
  const language = normalizeLanguageTag(languageTag)?.split("-")[0].toLowerCase();
  const copy: Record<string, { lang: string; title: string; before: string; after: string; confirm: string; cancel: string; canceled: string }> = {
    en: { lang: "en", title: "Review trip changes before saving", before: "Before", after: "Proposed", confirm: "Confirm changes", cancel: "Cancel", canceled: "Changes were not saved." },
    vi: { lang: "vi", title: "Xem lại thay đổi trước khi lưu", before: "Hiện tại", after: "Đề xuất", confirm: "Xác nhận thay đổi", cancel: "Hủy", canceled: "Các thay đổi chưa được lưu." },
    fr: { lang: "fr", title: "Vérifiez les changements avant l’enregistrement", before: "Actuel", after: "Proposé", confirm: "Confirmer les changements", cancel: "Annuler", canceled: "Les changements n’ont pas été enregistrés." },
    zh: { lang: "zh", title: "保存前请检查行程更改", before: "当前", after: "建议", confirm: "确认更改", cancel: "取消", canceled: "更改尚未保存。" },
    ja: { lang: "ja", title: "保存前に変更内容を確認してください", before: "現在", after: "提案", confirm: "変更を確認", cancel: "キャンセル", canceled: "変更は保存されていません。" },
    ar: { lang: "ar", title: "راجع تغييرات الرحلة قبل الحفظ", before: "الحالي", after: "المقترح", confirm: "تأكيد التغييرات", cancel: "إلغاء", canceled: "لم يتم حفظ التغييرات." },
  };
  return copy[language ?? ""] ?? copy.en;
}

function reviewValue(value: unknown, present: boolean | undefined): string {
  if (present === false) return "—";
  if (value === undefined || value === null) return "—";
  return typeof value === "string" ? value : JSON.stringify(value) ?? String(value);
}

function BriefConfirmationReview({
  confirmation, languageTag, formatChanges, onConfirm, onCancel, disabled,
}: {
  confirmation: GuestBriefConfirmation;
  languageTag: string;
  formatChanges?: (changes: readonly GuestBriefConfirmationChange[]) => readonly GuestBriefConfirmationLine[];
  onConfirm: () => void;
  onCancel: () => void;
  disabled: boolean;
}) {
  const copy = confirmationText(languageTag);
  const lines = formatChanges?.(confirmation.changes) ?? confirmation.changes.map((change) => ({
    field: change.field,
    before: reviewValue(change.before, change.before_present),
    after: reviewValue(change.after, change.after_present),
  }));
  return <section className="brief-confirmation" aria-label={copy.title}
    dir={directionForLanguageTag(languageTag)}>
    <h2 lang={copy.lang} dir={directionForLanguageTag(copy.lang)}>{copy.title}</h2>
    <ul>
      {lines.map((line, index) => <li key={`${line.field}-${index}`}>
        <strong lang="en" dir="auto">{line.field}</strong>
        <span lang="en" dir="auto">{copy.before}: {line.before}</span>
        <span lang="en" dir="auto">{copy.after}: {line.after}</span>
      </li>)}
    </ul>
    <button type="button" lang={copy.lang} disabled={disabled} onClick={onConfirm}>{copy.confirm}</button>
    <button type="button" lang={copy.lang} disabled={disabled} onClick={onCancel}>{copy.cancel}</button>
  </section>;
}

export function GuestChat({
  hotelSlug,
  brand,
  syntheticDisclosure,
  AnswerRenderer,
  GuestBriefRenderer,
  formatBriefConfirmationChanges,
  TurnResultRenderer,
  TurnResultActions: turnResultActions,
  target,
}: {
  hotelSlug: string;
  brand: string;
  syntheticDisclosure: string;
  AnswerRenderer: ComponentType<AnswerRendererProps>;
  GuestBriefRenderer: ComponentType<GuestBriefRendererProps>;
  formatBriefConfirmationChanges?: (changes: readonly GuestBriefConfirmationChange[]) => readonly GuestBriefConfirmationLine[];
  TurnResultRenderer: ComponentType<GuestTurnResultRendererProps>;
  TurnResultActions?: TurnResultActions;
  target: DomainTarget;
}) {
  const [session, setSession] = useState<GuestSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [sessionErrorRetryable, setSessionErrorRetryable] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [guestBrief, setGuestBrief] = useState<GuestBriefSnapshot | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [roomAdvicePending, setRoomAdvicePending] = useState<string | null>(null);
  const [roomAdviceError, setRoomAdviceError] = useState("");
  const turnsRef = useRef<ChatTurn[]>([]);
  const freshnessInFlight = useRef(new Set<string>());
  const generation = useRef(0);
  const briefVersion = useRef(-1);
  const activeRequest = useRef<number | null>(null);
  const hotelName = typeof session?.hotel.name === "string"
    ? session.hotel.name
    : hotelSlug.replaceAll("-", " ");

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  const acceptBrief = useCallback((brief: GuestBriefSnapshot | undefined, expectedGeneration: number) => {
    if (!brief || !isCurrentGeneration(expectedGeneration, generation.current)) return;
    if (brief.brief_version < briefVersion.current) return;
    briefVersion.current = brief.brief_version;
    setGuestBrief(brief);
  }, []);

  const openSession = useCallback(async (expectedGeneration: number) => {
    setSession(null);
    briefVersion.current = -1;
    setGuestBrief(null);
    setSessionError("");
    setSessionErrorRetryable(false);
    setSessionLoading(true);
    try {
      const created = await createGuestSession({ hotelSlug, target });
      if (generation.current === expectedGeneration) setSession(created);
    } catch (error) {
      if (generation.current === expectedGeneration) {
        const failure = classifySessionFailure(error instanceof ApiError ? error : { outcome: "unknown" });
        setSessionError(failure.message);
        setSessionErrorRetryable(failure.retryable);
      }
    } finally {
      if (generation.current === expectedGeneration) setSessionLoading(false);
    }
  }, [hotelSlug, target]);

  useEffect(() => {
    const current = ++generation.current;
    void openSession(current);
    return () => {
      generation.current += 1;
    };
  }, [hotelSlug, openSession]);

  const deliver = useCallback(async (turn: ChatTurn, id: string, answerOnlyReceiptId?: string) => {
    const currentGeneration = generation.current;
    const activeSession = session;
    if (!activeSession || !claimRequest(currentGeneration, activeRequest)) return;
    const refreshPreviousAnswers = async () => {
      const previousAnswers = turnsRef.current.filter((item) => item.id !== turn.id && item.answer);
      await Promise.all(previousAnswers.map(async (item) => {
        try {
          const freshness = await checkGuestFreshness({
            sessionId: activeSession.session_id, accessToken: activeSession.access_token,
            requestId: item.answer!.request_id, target,
          });
          if (!isCurrentGeneration(currentGeneration, generation.current)) return;
          const stale = freshness.status === "stale"
            || freshness.room_advice_currentness === "stale";
          setTurns((current) => current.map((existing) => existing.id === item.id
            ? { ...existing, stale, freshnessError: undefined } : existing));
        } catch {
          if (!isCurrentGeneration(currentGeneration, generation.current)) return;
          setTurns((current) => current.map((existing) => existing.id === item.id
            ? { ...existing, stale: true, freshnessError: "Could not verify whether this answer is still current." }
            : existing));
        }
      }));
    };
    setBusy(true);
    setTurns((current) => current.map((item) => item.id === turn.id
      ? { ...item, sending: true, error: undefined, retryMode: undefined }
      : item));
    try {
      const answer = await sendGuestMessage({
        sessionId: activeSession.session_id,
        accessToken: activeSession.access_token,
        requestId: id,
        question: answerOnlyReceiptId ? undefined : turn.question,
        answerOnlyReceiptId,
        target,
      });
      if (!isCurrentGeneration(currentGeneration, generation.current)) return;
      acceptBrief(answer.guest_brief, currentGeneration);
      if (answer.presentation) {
        labelsForLanguage(answer.presentation.language_tag, answer.presentation.labels);
      }
      if (answer.language_preference) {
        setSession((current) => {
          if (!current) return current;
          const currentRevision = current.language_preference?.revision ?? -1;
          return answer.language_preference!.revision < currentRevision
            ? current
            : { ...current, language_preference: answer.language_preference };
        });
      }
      if (answer.status === "partial_success") {
        const partialReceipt = answer.brief_receipt ?? null;
        setTurns((current) => current.map((item) => item.id === turn.id
          ? { ...item, id, answerOnlyReceiptId, receipt: partialReceipt,
              appliedDelta: answer.applied_delta ?? partialReceipt?.applied_delta,
              briefSnapshot: answer.guest_brief ?? item.briefSnapshot,
              resumeReceiptId: partialReceipt?.request_id,
              partialSuccess: true, sending: false,
              sameIdOnly: false,
              error: "Your trip details were updated, but the answer did not finish.", retryMode: undefined }
          : item));
        await refreshPreviousAnswers();
        return;
      }
      if (answer.status === "confirmation_required" && answer.brief_confirmation) {
        setTurns((current) => current.map((item) => item.id === turn.id
          ? { ...item, id, answer, briefConfirmation: answer.brief_confirmation,
              confirmationDismissed: false, sending: false, error: undefined, retryMode: undefined }
          : item));
        return;
      }
      setTurns((current) => {
        const completed = current.map((item) => item.id === turn.id
          ? { ...item, id, answer, receipt: answer.brief_receipt ?? item.receipt,
            answerOnlyReceiptId,
            briefSnapshot: answer.guest_brief ?? item.briefSnapshot,
            appliedDelta: answer.applied_delta ?? item.appliedDelta,
            resumeReceiptId: undefined, partialSuccess: false,
            recovered: false,
            sameIdOnly: false,
            stale: answer.brief_narrative_stale === true
              || (answer.brief_version_used !== undefined && answer.guest_brief !== undefined
                && answer.brief_version_used !== answer.guest_brief.brief_version),
            sending: false, error: undefined, retryMode: undefined }
          : item);
        return answerOnlyReceiptId
          ? resolveAnswerOnlyReceipt(completed, answerOnlyReceiptId, id)
          : completed;
      });
      await refreshPreviousAnswers();
    } catch (error) {
      if (!isCurrentGeneration(currentGeneration, generation.current)) return;
      const partial = error instanceof ApiError ? error.partialResult : undefined;
      if (partial) acceptBrief(partial.guest_brief, currentGeneration);
      const display = classifyFailure(error instanceof ApiError
        ? error
        : { outcome: "unknown" });
      const errorCode = error instanceof ApiError ? error.code : undefined;
      setTurns((current) => current.map((item) => item.id === turn.id
        ? { ...item, id, sending: false,
            answerOnlyReceiptId,
            sameIdOnly: partial ? false : errorCode === "brief_apply_no_effect" || errorCode === "request_failed" ? false
              : item.sameIdOnly || errorCode === "brief_apply_outcome_unknown",
            error: partial ? "Your trip details were updated, but the answer did not finish." : display.message,
            receipt: partial?.brief_receipt ?? item.receipt,
            briefSnapshot: partial?.guest_brief ?? item.briefSnapshot,
            appliedDelta: partial?.applied_delta ?? item.appliedDelta,
            resumeReceiptId: partial?.brief_receipt.request_id ?? item.resumeReceiptId,
            partialSuccess: Boolean(partial),
            retryMode: partial ? undefined
              : errorCode === "brief_apply_no_effect" || errorCode === "request_failed" ? display.retryMode
                : item.sameIdOnly || errorCode === "brief_apply_outcome_unknown"
                  ? "same-request" : retryModeForFailure(display.retryMode, false) }
        : item));
    } finally {
      if (isCurrentGeneration(currentGeneration, generation.current)) setBusy(false);
      releaseRequest(currentGeneration, activeRequest);
    }
  }, [acceptBrief, session, target]);

  const unresolvedRequest = hasUnresolvedRequest(turns)
    || turns.some((turn) => Boolean(turn.briefConfirmation) && !turn.confirmationDismissed);

  const recheckAnswer = useCallback(async (turnId: string, response: GuestMessageResponse) => {
    if (!session || freshnessInFlight.current.has(response.request_id)) return;
    const currentGeneration = generation.current;
    freshnessInFlight.current.add(response.request_id);
    try {
      const result = await checkGuestFreshness({
        sessionId: session.session_id,
        accessToken: session.access_token,
        requestId: response.request_id,
        target,
      });
      if (!isCurrentGeneration(currentGeneration, generation.current)) return;
      const serverStale = result.status === "stale" || result.room_advice_currentness === "stale";
      setTurns((current) => current.map((item) => item.id === turnId
        ? { ...item, stale: serverStale, freshnessError: undefined }
        : item));
    } catch {
      if (!isCurrentGeneration(currentGeneration, generation.current)) return;
      setTurns((current) => current.map((item) => item.id === turnId
        ? { ...item, stale: true, freshnessError: "Could not verify whether this answer is still current." }
        : item));
    } finally {
      freshnessInFlight.current.delete(response.request_id);
    }
  }, [session, target]);

  const recheckVisibleAnswers = useCallback(async () => {
    const current = turnsRef.current;
    await Promise.all(current.filter((item) => item.answer)
      .map((item) => recheckAnswer(item.id, item.answer!)));
  }, [recheckAnswer]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void recheckVisibleAnswers();
    };
    const onPageShow = () => void recheckVisibleAnswers();
    const onFocus = () => void recheckVisibleAnswers();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("focus", onFocus);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("focus", onFocus);
    };
  }, [recheckVisibleAnswers]);

  function startNewChat() {
    if (sessionLoading) return;
    setTurns([]);
    setGuestBrief(null);
    briefVersion.current = -1;
    setQuestion("");
    const current = ++generation.current;
    setBusy(false);
    void openSession(current);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text || !canStartRequest(Boolean(session), activeRequest.current === generation.current, unresolvedRequest)) return;
    const turn: ChatTurn = {
      id: requestId(), question: text, sending: true,
      languageTag: session?.language_preference?.language_tag ?? "en",
      scopeSessionId: session?.session_id,
    };
    setTurns((current) => [...current, turn]);
    setQuestion("");
    void (async () => {
      setBusy(true);
      await recheckVisibleAnswers();
      await deliver(turn, turn.id);
    })();
  }

  function retry(turn: ChatTurn) {
    if (!session || !turn.retryMode) return;
    if (turn.retryMode === "new-session") {
      startNewChat();
      return;
    }
    if (turn.retryMode === "same-request") {
      void deliver(turn, turn.id, turn.answerOnlyReceiptId);
      return;
    }
    if (turn.retryMode === "new-request") {
      const nextId = requestId();
      void deliver(turn, nextId, turn.answerOnlyReceiptId);
    }
  }

  function resumeAnswer(turn: ChatTurn) {
    if (!turn.resumeReceiptId || !session || busy) return;
    const resumeTurn: ChatTurn = {
      id: requestId(), question: "Continue the answer using the saved trip details.",
      sending: true, answerOnlyReceiptId: turn.resumeReceiptId,
      scopeSessionId: session.session_id,
    };
    setTurns((current) => [...current, resumeTurn]);
    void deliver(resumeTurn, resumeTurn.id, turn.resumeReceiptId);
  }

  async function confirmBriefUpdate(turn: ChatTurn) {
    const challenge = turn.briefConfirmation;
    if (!session || !challenge || busy || !claimRequest(generation.current, activeRequest)) return;
    const currentGeneration = generation.current;
    const confirmRequestId = turn.confirmationRequestId ?? requestId();
    setBusy(true);
    setTurns((current) => current.map((item) => item.id === turn.id
      ? { ...item, sending: true, error: undefined }
      : item));
    try {
      const response = await confirmGuestBriefEdit({
        sessionId: session.session_id,
        accessToken: session.access_token,
        requestId: confirmRequestId,
        confirmationToken: challenge.token,
        target,
      });
      if (!isCurrentGeneration(currentGeneration, generation.current)) return;
      acceptBrief(response.guest_brief, currentGeneration);
      setTurns((current) => current.map((item) => item.id === turn.id
        ? { ...item, id: confirmRequestId, answer: response, briefConfirmation: undefined,
            confirmationRequestId: undefined, retryMode: undefined,
            receipt: response.brief_receipt ?? item.receipt,
            appliedDelta: response.applied_delta ?? item.appliedDelta,
            briefSnapshot: response.guest_brief ?? item.briefSnapshot,
            resumeReceiptId: response.status === "partial_success" ? response.brief_receipt?.request_id : undefined,
            partialSuccess: response.status === "partial_success", sending: false,
            error: response.status === "partial_success"
              ? "Your trip details were updated, but the answer did not finish." : undefined }
        : item));
    } catch (error) {
      if (!isCurrentGeneration(currentGeneration, generation.current)) return;
      const partial = error instanceof ApiError ? error.partialResult : undefined;
      if (partial) acceptBrief(partial.guest_brief, currentGeneration);
      const failure = classifyFailure(error instanceof ApiError ? error : { outcome: "unknown" });
      const errorCode = error instanceof ApiError ? error.code : undefined;
      setTurns((current) => current.map((item) => item.id === turn.id
        ? { ...item, sending: false,
            error: partial ? "Your trip details were updated, but the answer did not finish." : failure.message,
            receipt: partial?.brief_receipt ?? item.receipt,
            briefSnapshot: partial?.guest_brief ?? item.briefSnapshot,
            appliedDelta: partial?.applied_delta ?? item.appliedDelta,
            resumeReceiptId: partial?.brief_receipt.request_id ?? item.resumeReceiptId,
            partialSuccess: Boolean(partial), briefConfirmation: partial ? undefined : item.briefConfirmation,
            confirmationRequestId: partial || errorCode === "brief_apply_no_effect" ? undefined : confirmRequestId,
            retryMode: partial ? undefined : failure.retryMode }
        : item));
    } finally {
      if (isCurrentGeneration(currentGeneration, generation.current)) setBusy(false);
      releaseRequest(currentGeneration, activeRequest);
    }
  }

  function cancelBriefUpdate(turnId: string) {
    setTurns((current) => current.map((item) => item.id === turnId
      ? { ...item, briefConfirmation: undefined, confirmationDismissed: true }
      : item));
  }

  async function selectTurnResultOption(turnId: string, result: unknown, optionId: string) {
    if (!session || !turnResultActions || roomAdvicePending || busy) return;
    setRoomAdvicePending(optionId);
    setRoomAdviceError("");
    try {
      const selection = await turnResultActions.selectOption({
        sessionId: session.session_id, accessToken: session.access_token, result, optionId, target,
      });
      setTurns((current) => current.map((turn) => {
        if (turn.id !== turnId || !turn.answer) return turn;
        return { ...turn, answer: turnResultActions.attachSelection(turn.answer, result, selection) as GuestMessageResponse };
      }));
    } catch {
      setRoomAdviceError("room_selection_failed");
    } finally {
      setRoomAdvicePending(null);
    }
  }

  const activeLanguageTag = session?.language_preference?.language_tag ?? "en";
  const activeLabels = labelsForLanguage(activeLanguageTag);
  const showEnglishLabelFallback = normalizeLanguageTag(activeLanguageTag)?.split("-")[0].toLowerCase() !== "en"
    && !hasCompleteLabelBundle(activeLanguageTag);

  return (
    <main className="chat-shell" lang={session?.language_preference?.language_tag ?? "en"}
      dir={directionForLanguageTag(session?.language_preference?.language_tag ?? "en")}>
      <header className="chat-header">
        <Link className="back-link" href="/">{brand}</Link>
        <p className="synthetic-label">{activeLabels.synthetic_notice || syntheticDisclosure}</p>
        {showEnglishLabelFallback && <p className="status-note" lang="en" dir="ltr" role="note">
          Some interface labels are shown in English because translations are unavailable.
        </p>}
        <h1>{hotelName}</h1>
        <p className="chat-intro">{activeLabels.ai_notice}</p>
        <TurnResultRenderer response={null} bookingChannel={session?.hotel.booking_channel ?? null}
          languageTag={activeLanguageTag} stale={false} freshnessError={false}
          selectionDisabled={busy} pendingOptionId={roomAdvicePending} selectionError=""
          onSelectOption={selectTurnResultOption} />
        {guestBrief && guestBrief.brief_version > 0 && <div lang={session?.language_preference?.language_tag ?? "en"}
          dir={directionForLanguageTag(session?.language_preference?.language_tag ?? "en")}>
          <GuestBriefRenderer brief={guestBrief} labels={activeLabels} />
        </div>}
      </header>

      <section className="chat-panel" aria-label={`Chat with ${hotelName}`}>
        <div className="chat-transcript" aria-live="polite" aria-relevant="additions text">
          {!turns.length && sessionLoading && <p className="status-note">Starting a new private chat…</p>}
          {!turns.length && session && <p className="status-note">Ask a question about {hotelName} to get started.</p>}
          {turns.map((turn) => (
            <article className="turn" key={`${turn.id}-${turn.question}`}>
              <div className="message message-guest" lang={turn.languageTag ?? "en"} dir="auto"><p>{turn.question}</p></div>
              {turn.briefConfirmation && !turn.confirmationDismissed && <BriefConfirmationReview
                confirmation={turn.briefConfirmation}
                languageTag={turn.languageTag ?? activeLanguageTag}
                formatChanges={formatBriefConfirmationChanges}
                disabled={busy}
                onConfirm={() => void confirmBriefUpdate(turn)}
                onCancel={() => cancelBriefUpdate(turn.id)}
              />}
              {turn.confirmationDismissed && <p className="status-note" role="status">
                {confirmationText(turn.languageTag ?? activeLanguageTag).canceled}
              </p>}
              {turn.sending && <p className="status-note">{activeLabels.sending}</p>}
              {turn.recovered && <p className="status-note" role="status">
                This saved answer was completed by a later continuation.
              </p>}
              {turn.error && (
                <div className="message message-error" role="status">
                  <p>{turn.partialSuccess
                    ? activeLabels.partial_success
                    : turn.error}</p>
                  {turn.partialSuccess && turn.resumeReceiptId && (
                    <button className="text-button" type="button" onClick={() => resumeAnswer(turn)} disabled={busy || !session}>
                      Continue the answer using the updated trip details
                    </button>
                  )}
                  {turn.retryMode && turn.retryMode !== "none" && (
                    <button className="text-button" type="button"
                      onClick={() => turn.briefConfirmation ? void confirmBriefUpdate(turn) : retry(turn)} disabled={busy || !session}>
                      {activeLabels.retry_answer}
                    </button>
                  )}
                  {turn.retryMode === "same-request" && (
                    <button className="text-button" type="button" onClick={startNewChat} disabled={sessionLoading}>
                      Start a new chat
                    </button>
                  )}
                </div>
              )}
              {turn.receipt && <>
                <details className="brief-receipt">
                  <summary>Trip update receipt · version {turn.receipt.brief_version_after}</summary>
                  <p>{turn.receipt.status === "applied" ? "The update was applied." : turn.receipt.status === "no_change"
                    ? "No trip details changed." : turn.receipt.status === "clarification"
                      ? "Some details still need clarification." : turn.receipt.answer_status === "completed"
                        ? "The update was applied and the answer has now completed." : "The update was applied, but the answer did not finish."}</p>
                  <p>Recorded at trip details version {turn.receipt.brief_version_after}; current details may have changed since.</p>
                  <GuestBriefRenderer brief={guestBrief ?? turn.briefSnapshot ?? {}} receipt={turn.receipt}
                    delta={turn.appliedDelta} labels={activeLabels} />
                </details>
              </>}
              {turn.answer && <TurnResultRenderer response={turn.answer} bookingChannel={session?.hotel.booking_channel ?? null}
                languageTag={turn.answer.presentation?.language_tag ?? turn.languageTag ?? "en"}
                localGuideLabels={turn.answer.presentation?.local_guide_labels}
                staleMessage={labelsForLanguage(
                  turn.answer.presentation?.language_tag ?? turn.languageTag ?? "en",
                  turn.answer.presentation?.labels,
                ).stale_answer}
                stale={turn.stale ?? false} freshnessError={Boolean(turn.freshnessError)}
                selectionDisabled={busy}
                pendingOptionId={roomAdvicePending} selectionError={roomAdviceError}
                turnId={turn.id} onSelectOption={selectTurnResultOption} />}
              {turn.answer && !!turn.answer.answer && <AnswerCard
                response={turn.answer}
                session={session}
                target={target}
                AnswerRenderer={AnswerRenderer}
                stale={turn.stale ?? false}
                freshnessError={turn.freshnessError}
                historicalLanguageTag={turn.answer.presentation?.language_tag ?? turn.languageTag ?? "en"}
                currentPreferenceRevision={session?.language_preference?.revision ?? -1}
                currentScopeSessionId={session?.session_id}
                isCurrentTurn={turns.at(-1)?.id === turn.id && !busy}
                onRecheck={() => void recheckAnswer(turn.id, turn.answer!)}
              />}
            </article>
          ))}
          {sessionError && (
            <div className="session-error" role="alert">
              <p>{sessionError}</p>
              {sessionErrorRetryable && (
                <button className="text-button" type="button" disabled={sessionLoading} onClick={() => {
                  const current = ++generation.current;
                  void openSession(current);
                }}>
                  Try again
                </button>
              )}
            </div>
          )}
        </div>

        <form className="chat-composer" onSubmit={submit}>
          <label htmlFor="guest-question">Your question</label>
          <div className="composer-row">
            <textarea
              id="guest-question"
              lang={session?.language_preference?.language_tag ?? "en"}
              dir="auto"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask in any language…"
              maxLength={2000}
              rows={2}
              disabled={!session || busy || unresolvedRequest}
              aria-describedby="question-hint"
              required
            />
            <button className="send-button" type="submit" disabled={!session || busy || unresolvedRequest || !question.trim()}>
              {activeLabels.send}
            </button>
          </div>
          {unresolvedRequest && <p className="composer-hint">Retry the pending request with the same ID, or start a new chat before asking another question.</p>}
          <p id="question-hint" className="composer-hint">Your conversation stays in this browser tab and starts fresh when reloaded.</p>
        </form>
      </section>
    </main>
  );
}

function AnswerCard({
  response,
  session,
  target,
  AnswerRenderer,
  stale,
  freshnessError,
  historicalLanguageTag,
  currentPreferenceRevision,
  currentScopeSessionId,
  isCurrentTurn,
  onRecheck,
}: {
  response: GuestMessageResponse;
  session: GuestSession | null;
  target: DomainTarget;
  AnswerRenderer: ComponentType<AnswerRendererProps>;
  stale: boolean;
  freshnessError?: string;
  historicalLanguageTag: string;
  currentPreferenceRevision: number;
  currentScopeSessionId?: string;
  isCurrentTurn: boolean;
  onRecheck: () => void;
}) {
  const [copyResult, setCopyResult] = useState<CopyResult | "">("");
  const answerText = response.answer ?? "";
  const answerNode = useRef<HTMLDivElement | null>(null);
  const answerLanguage = response.presentation?.language_tag ?? historicalLanguageTag;
  const answerDirection = response.presentation?.direction ?? directionForLanguageTag(answerLanguage);
  const labels = labelsForLanguage(answerLanguage, response.presentation?.labels);
  const showAnswerEnglishFallback = normalizeLanguageTag(answerLanguage)?.split("-")[0].toLowerCase() !== "en"
    && (response.presentation?.labels_fallback === true || !hasCompleteLabelBundle(answerLanguage));
  const answerStale = stale || response.answer_eligibility === "stale" || response.presentation?.freshness === "stale";
  const preferenceIsCurrent = response.presentation?.preference_revision === currentPreferenceRevision;
  const scopeIsCurrent = session?.session_id === currentScopeSessionId;
  const eligible = response.status === "completed"
    && response.answer_eligibility === "current"
    && !!answerText
    && !answerStale
    && !freshnessError
    && preferenceIsCurrent
    && scopeIsCurrent
    && isCurrentTurn;
  const displayedEligibility = answerStale || !isCurrentTurn || !scopeIsCurrent || !preferenceIsCurrent
    ? "stale" : eligible ? "current" : response.answer_eligibility ?? "pending";
  const copyAnswer = async () => {
    if (!eligible) return;
    const selectAnswer = () => {
      if (!eligibleRef.current) return false;
      const node = answerNode.current;
      if (!node || !window.getSelection) return false;
      const selection = window.getSelection();
      if (!selection) return false;
      const range = document.createRange();
      range.selectNodeContents(node);
      selection.removeAllRanges();
      selection.addRange(range);
      return true;
    };
    const textToCopy = answerNode.current?.textContent ?? answerText;
    setCopyResult("");
    const result = await copyPlainText(textToCopy, navigator.clipboard, selectAnswer);
    if (eligibleRef.current) setCopyResult(result);
  };
  const eligibleRef = useRef(eligible);
  useEffect(() => {
    eligibleRef.current = eligible;
  }, [eligible]);
  const copyStatus = copyResult === "copied" ? labels.copied
    : copyResult === "selection_fallback" ? "Answer selected. Use your browser’s copy command."
      : copyResult === "unsupported" ? "Clipboard is unavailable. Select the answer and copy it manually."
        : copyResult === "failed" ? labels.copy_failed : "";
  return (
    <div className="message message-assistant" lang={answerLanguage} dir={answerDirection}
      data-answer-eligibility={displayedEligibility} data-copy-eligible={String(eligible)}
      data-receipt-id={response.presentation?.receipt_id ?? undefined}>
      {showAnswerEnglishFallback && <p className="status-note" lang="en" dir="ltr" role="note">
        Some interface labels are shown in English because translations are unavailable.
      </p>}
      {answerStale && <p className="status-note" role="status">{labels.stale_answer}</p>}
      {freshnessError && <p className="status-note" role="status">{freshnessError}</p>}
      <div className="answer-actions">
        <button className="text-button" type="button" onClick={onRecheck}>{labels.check_status}</button>
        <button className="text-button" type="button" onClick={() => void copyAnswer()} disabled={!eligible}>
          {labels.copy}
        </button>
      </div>
      <span className="copy-status" data-copy-result={copyResult || undefined}
        aria-live="polite" role={copyStatus ? "status" : undefined}>{copyStatus}</span>
      <div ref={answerNode} className="answer-copy-source">
        <AnswerRenderer answer={answerText} />
      </div>
      {!stale && !freshnessError && !!response.media?.length && session && (
        <div className="answer-media" aria-label="Approved hotel media">
          {response.media.map((media) => (
          <GuestMedia key={`${session.session_id}-${media.media_id}-${media.source_hash}`} media={media} session={session} target={target} />
          ))}
        </div>
      )}
      {!!response.unknowns?.length && (
        <div className="unknown-block">
          <h2>Could not confirm</h2>
          <ul>{response.unknowns?.map((unknown, index) => <li key={`${index}-${unknown}`}>{unknown}</li>)}</ul>
        </div>
      )}
      {!!response.evidence?.length && (
        <details className="evidence-list">
          <summary>Hotel records used ({response.evidence.length})</summary>
          <ul>
            {response.evidence?.map((item, index) => (
              <li key={`${item.fact_id}-${index}`}>
                <span>{item.section || "Hotel information"}</span>
                <small>Record {item.fact_id} · source {item.source_id} · version {item.source_version}</small>
                {item.imported_at && <small>Imported {item.imported_at}</small>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function GuestMedia({ media, session, target }: {
  media: GuestMediaDescriptor;
  session: GuestSession;
  target: DomainTarget;
}) {
  const [src, setSrc] = useState("");
  const [captionsSrc, setCaptionsSrc] = useState("");
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let live = true;
    const objectUrls: string[] = [];
    const load = async () => {
      try {
        const blob = await fetchGuestMedia({
          sessionId: session.session_id,
          media,
          accessToken: session.access_token,
          target,
          signal: controller.signal,
        });
        if (!live) return;
        const mediaUrl = URL.createObjectURL(blob);
        objectUrls.push(mediaUrl);
        setSrc(mediaUrl);
        if (media.captions_media_id) {
          const captions = await fetchGuestMedia({
            sessionId: session.session_id,
            media,
            mediaId: media.captions_media_id,
            sha256: media.captions_sha256,
            accessToken: session.access_token,
            target,
            signal: controller.signal,
          });
          if (!live) return;
          const captionsUrl = URL.createObjectURL(captions);
          objectUrls.push(captionsUrl);
          setCaptionsSrc(captionsUrl);
        }
      } catch {
        if (live && !controller.signal.aborted) setError("Approved media is temporarily unavailable.");
      }
    };
    void load();
    return () => {
      live = false;
      controller.abort();
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [media, session.session_id, session.access_token, target]);

  const timeReference = media.start_seconds !== undefined
    ? `${formatMediaTime(media.start_seconds)}${media.end_seconds !== undefined ? `–${formatMediaTime(media.end_seconds)}` : ""}`
    : "";
  return (
    <figure className="media-evidence">
      {media.kind === "image" && src && <img src={src} alt={media.alt_text} /> /* eslint-disable-line @next/next/no-img-element */}
      {media.kind === "video" && src && (
        <video ref={video} controls preload="metadata" aria-label={media.alt_text}>
          <source src={src} type="video/mp4" />
          {captionsSrc && <track kind="captions" src={captionsSrc} srcLang="en" label="Captions" default />}
        </video>
      )}
      {error && <p role="status">{error}</p>}
      <figcaption>
        <span>{media.caption}</span>
        {timeReference && <button type="button" className="text-button" onClick={() => {
          if (video.current) {
            video.current.currentTime = media.start_seconds ?? 0;
            void video.current.play();
          }
        }}>Play from {timeReference}</button>}
      </figcaption>
    </figure>
  );
}

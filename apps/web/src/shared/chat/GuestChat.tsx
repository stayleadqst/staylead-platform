"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { ComponentType } from "react";
import Link from "next/link";
import type { AnswerRendererProps, GuestBriefRendererProps, GuestTurnResultRendererProps, TurnResultActions, DomainTarget } from "@/composition/registration";
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
  checkGuestFreshness,
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
  sameIdOnly?: boolean;
  languageTag?: string;
  scopeSessionId?: string;
};

function requestId() {
  return crypto.randomUUID();
}

export function GuestChat({
  hotelSlug,
  brand,
  syntheticDisclosure,
  AnswerRenderer,
  GuestBriefRenderer,
  TurnResultRenderer,
  TurnResultActions: turnResultActions,
  target,
}: {
  hotelSlug: string;
  brand: string;
  syntheticDisclosure: string;
  AnswerRenderer: ComponentType<AnswerRendererProps>;
  GuestBriefRenderer: ComponentType<GuestBriefRendererProps>;
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

  const unresolvedRequest = hasUnresolvedRequest(turns);

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
                    <button className="text-button" type="button" onClick={() => retry(turn)} disabled={busy || !session}>
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

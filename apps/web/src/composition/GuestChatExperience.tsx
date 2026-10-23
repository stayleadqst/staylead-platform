"use client";

import { useMemo } from "react";

import { resolveConfiguredTarget, resolveDomainRegistration } from "@/composition/registration";
import { GuestChat } from "@/shared/chat/GuestChat";

export function GuestChatExperience({ hotelSlug }: { hotelSlug: string }) {
  const { target, registration } = useMemo(() => {
    const selectedTarget = resolveConfiguredTarget();
    return {
      target: selectedTarget,
      registration: resolveDomainRegistration(selectedTarget),
    };
  }, []);
  const AnswerRenderer = registration.answerRenderer;

  return (
    <div className={registration.themeClass}>
      <GuestChat
        key={hotelSlug}
        hotelSlug={hotelSlug}
        target={target}
        brand={registration.content.brand}
        syntheticDisclosure={registration.content.syntheticDisclosure}
        AnswerRenderer={AnswerRenderer}
      />
    </div>
  );
}

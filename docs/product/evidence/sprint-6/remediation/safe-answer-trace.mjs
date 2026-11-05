/** Keep only backend answer-validation summary fields; never retain rejected content. */
export function safeAnswerTrace(value) {
  if (!value || typeof value !== "object") return null;
  const answerValidation = value.answer_validation;
  const guestClaimsRejected = value.guest_claims_rejected;
  return {
    answer_validation: answerValidation === "fully_validated" || answerValidation === "safe_portion"
      ? answerValidation : null,
    guest_claims_rejected: Number.isSafeInteger(guestClaimsRejected) && guestClaimsRejected >= 0 && guestClaimsRejected <= 10000
      ? guestClaimsRejected : null,
  };
}

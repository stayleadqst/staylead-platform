/** Pure routing decision shared by the real browser driver and offline tests. */
export function shouldOfferOperatorResume({ responseReceived, httpStatus, apiStatus, receiptId }) {
  return responseReceived === true &&
    Number.isInteger(httpStatus) && httpStatus >= 200 && httpStatus <= 599 &&
    apiStatus === "partial_success" &&
    typeof receiptId === "string" && receiptId.length > 0 && receiptId.length <= 512;
}

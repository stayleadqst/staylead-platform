export type RoomAdviceCostViewInput = Readonly<{
  status: string;
  total: number | null;
  nightly_subtotal: number | null;
}>;

export function roomAdviceCostView(cost: RoomAdviceCostViewInput): Readonly<{
  confirmedStayTotal: number | null;
  referenceNightlyBase: number | null;
}> {
  return {
    confirmedStayTotal: cost.status === "complete" ? cost.total : null,
    referenceNightlyBase: cost.nightly_subtotal,
  };
}

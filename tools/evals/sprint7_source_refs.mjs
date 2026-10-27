/** Strict public-wire source binding checks for the Sprint 7 browser harness. */
export function validateSourceRefs(room, sourceOwner, factOwner) {
  if (!Array.isArray(room?.source_refs) || room.source_refs.length === 0) return false;
  for (const sourceRef of room.source_refs) {
    const source = sourceRef.source ?? sourceRef;
    const owner = sourceOwner.get(source.source_id);
    const generation = source.source_generation ?? source.hotel_generation;
    const factIds = sourceRef.fact_ids ?? (sourceRef.fact_id ? [sourceRef.fact_id] : []);
    if (!owner || owner.hotel_id !== room.hotel_id
        || (source.hotel_id && source.hotel_id !== room.hotel_id)
        || source.source_version !== owner.version
        || !/^[a-f0-9]{64}$/u.test(source.source_hash ?? "")
        || source.source_hash !== owner.expected_hash
        || generation !== owner.source_generation
        || generation !== room.source_generation
        || factIds.length === 0
        || !factIds.every((id) => factOwner.get(id)?.hotel_id === room.hotel_id
          && factOwner.get(id)?.source_id === source.source_id)) return false;
  }
  return true;
}

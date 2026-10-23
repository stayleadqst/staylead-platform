import { resolveConfiguredTarget, resolveDomainRegistration } from "@/composition/registration";
import { GuestChatExperience } from "@/composition/GuestChatExperience";

type HotelChatPageProps = Readonly<{
  params: Promise<{ hotelSlug: string }>;
}>;

export default async function HotelChatPage({ params }: HotelChatPageProps) {
  const { hotelSlug } = await params;
  const target = resolveConfiguredTarget();
  // Admission is data-driven by the guest API; unknown slugs are reported by lookup.
  resolveDomainRegistration(target);

  return (
    <GuestChatExperience hotelSlug={hotelSlug} />
  );
}

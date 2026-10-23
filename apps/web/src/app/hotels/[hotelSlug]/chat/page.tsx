import { notFound } from "next/navigation";

import { resolveConfiguredTarget, resolveDomainRegistration } from "@/composition/registration";
import { GuestChatExperience } from "@/composition/GuestChatExperience";

type HotelChatPageProps = Readonly<{
  params: Promise<{ hotelSlug: string }>;
}>;

export default async function HotelChatPage({ params }: HotelChatPageProps) {
  const { hotelSlug } = await params;
  const target = resolveConfiguredTarget();
  const registration = resolveDomainRegistration(target);
  if (!registration.content.demoHotelSlugs.includes(hotelSlug)) notFound();

  return (
    <GuestChatExperience hotelSlug={hotelSlug} />
  );
}

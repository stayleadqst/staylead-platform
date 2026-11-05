import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  logging: { incomingRequests: { ignore: [/^\/api\/operator\/auth\/callback(?:\?|$)/] } },
};

export default nextConfig;

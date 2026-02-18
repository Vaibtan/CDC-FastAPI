/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Ensure server components can fetch from internal services
  experimental: {
    serverActions: {
      allowedOrigins: ['localhost:3000'],
    },
  },
};

export default nextConfig;

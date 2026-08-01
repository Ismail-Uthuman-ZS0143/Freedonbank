/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        // Proxies browser fetch('/api/...') calls to the Django backend --
        // same pattern as appstore/frontend, so the session cookie stays
        // same-origin from the browser's perspective.
        source: '/api/:path*',
        destination: 'http://localhost:8001/api/:path*',
      },
    ];
  },
};

export default nextConfig;

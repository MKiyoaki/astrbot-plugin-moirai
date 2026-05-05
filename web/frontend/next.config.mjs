/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  distDir: 'output',
  images: {
    unoptimized: true,
  },

  trailingSlash: true,

  async rewrites() {
    const backendPort = process.env.BACKEND_PORT || '2653'
    return [
      {
        source: '/api/:path*',
        destination: `http://localhost:${backendPort}/api/:path*`,
      },
    ]
  },
};

export default nextConfig;
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  distDir: 'output',
  images: {
    unoptimized: true,
  },

  trailingSlash: true,

};

export default nextConfig;
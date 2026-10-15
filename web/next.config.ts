import type { NextConfig } from 'next';

// 'standalone' produces a self-contained server for the Docker image
const nextConfig: NextConfig = { output: 'standalone' };

export default nextConfig;

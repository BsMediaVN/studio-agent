'use client';

import { useRef, useEffect } from 'react';

interface VisualizerProps {
  isPlaying: boolean;
  analyserNode: AnalyserNode | null;
}

export function Visualizer({ isPlaying, analyserNode }: VisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const renderFrame = () => {
      const canvas = canvasRef.current;
      const analyser = analyserNode;
      if (!canvas || !analyser) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      analyser.getByteFrequencyData(dataArray);

      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth || 600;
      const height = canvas.clientHeight || 120;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const barCount = 64;
      const step = Math.max(1, Math.floor(bufferLength / barCount));
      const barWidth = width / barCount;
      const maxHeight = height - 12;

      const gradient = ctx.createLinearGradient(0, height, 0, 0);
      gradient.addColorStop(0, 'rgba(45,212,191,0.9)');
      gradient.addColorStop(0.55, 'rgba(245,158,11,0.9)');
      gradient.addColorStop(1, 'rgba(251,113,133,0.85)');

      ctx.shadowColor = 'rgba(45,212,191,0.4)';
      ctx.shadowBlur = 18;

      for (let i = 0; i < barCount; i++) {
        const value = dataArray[i * step];
        const barHeight = Math.max(6, (value / 255) * maxHeight);
        const x = i * barWidth;
        ctx.globalAlpha = 0.35 + (value / 255) * 0.65;
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x + 1.5, height - barHeight, barWidth - 3, barHeight, 6);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      rafRef.current = requestAnimationFrame(renderFrame);
    };

    if (isPlaying) {
      renderFrame();
    } else {
      cancelAnimationFrame(rafRef.current);
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
    }

    return () => cancelAnimationFrame(rafRef.current);
  }, [isPlaying, analyserNode]);

  return (
    <div className="visualizer-card h-32 flex items-end justify-center">
      <div className="visualizer-label">Live Spectrum</div>
      <canvas ref={canvasRef} width={600} height={100} className="w-full h-full" />
    </div>
  );
}

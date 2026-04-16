/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,ts}',
  ],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {},
  },
  plugins: [require('daisyui')],
  daisyui: {
    themes: [
      {
        vcrc: {
          "primary":         "#172429",
          "primary-content": "#ffffff",
          "secondary":       "#4b5563",
          "accent":          "#3b82f6",
          "neutral":         "#374151",
          "base-100":        "#ffffff",
          "base-200":        "#f9fafb",
          "base-300":        "#e5e7eb",
          "base-content":    "#111827",
          "info":            "#3b82f6",
          "success":         "#22c55e",
          "warning":         "#f59e0b",
          "error":           "#ef4444",
        },
      },
    ],
    logs: false,
  },
};

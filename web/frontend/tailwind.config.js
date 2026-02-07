/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Primary: Teal/Cyan (Remnawave brand)
        primary: {
          50: '#ecfeff',
          100: '#cffafe',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
          950: '#083344',
        },
        // Dark palette: GitHub-inspired
        dark: {
          50: '#c9d1d9',
          100: '#b1bac4',
          200: '#8b949e',
          300: '#6e7681',
          400: '#484f58',
          500: '#30363d',
          600: '#21262d',
          700: '#161b22',
          800: '#0d1117',
          900: '#010409',
          950: '#000000',
        },
        // Accent teal for glows and highlights
        accent: {
          teal: '#0d9488',
          cyan: '#06b6d4',
        },
      },
      fontFamily: {
        sans: ['Montserrat', 'system-ui', 'sans-serif'],
        mono: ['Fira Mono', 'JetBrains Mono', 'monospace'],
        display: ['Unbounded', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeInDown: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        slideDown: {
          '0%': { opacity: '0', maxHeight: '0' },
          '100%': { opacity: '1', maxHeight: '500px' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        slideInLeft: {
          '0%': { transform: 'translateX(-8px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 15px -3px rgba(20, 184, 166, 0.3)' },
          '50%': { boxShadow: '0 0 25px -3px rgba(20, 184, 166, 0.5)' },
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'fade-in-up': 'fadeInUp 0.35s ease-out both',
        'fade-in-down': 'fadeInDown 0.3s ease-out both',
        'scale-in': 'scaleIn 0.25s ease-out both',
        'slide-down': 'slideDown 0.3s ease-out both',
        'shimmer': 'shimmer 1.5s infinite',
        'slide-in': 'slideInLeft 0.3s ease-out',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
      },
      boxShadow: {
        'glow-teal': '0 0 30px -5px rgba(20, 184, 166, 0.3)',
        'glow-teal-lg': '0 0 40px -5px rgba(20, 184, 166, 0.4)',
        'deep': '0 8px 32px rgba(0, 0, 0, 0.4)',
        'card': '0 4px 16px rgba(0, 0, 0, 0.2)',
      },
    },
  },
  plugins: [],
}

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx}', './components/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#0b0d12',
        panel: '#12151d',
        edge: '#1f2430',
        accent: '#6d8dff',
      },
    },
  },
  plugins: [],
};

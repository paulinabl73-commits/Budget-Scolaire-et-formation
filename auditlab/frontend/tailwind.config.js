/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        marque: { 50: "#eef4fb", 100: "#d5e3f4", 600: "#1f5fa8", 700: "#184c87", 900: "#0f2c4f" },
      },
    },
  },
  plugins: [],
};

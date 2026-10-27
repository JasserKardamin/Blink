/** Charte graphique Blink (présentation, diapositive 17). */
module.exports = {
  content: ["./templates/**/*.html", "./**/templatetags/*.py", "./static/js/**/*.js", "./**/forms.py"],
  theme: {
    extend: {
      colors: {
        maya: "#66C5FF", // Maya Blue
        midnight: "#13112A", // Midnight Violet
        peri: "#8B7BFF", // Soft Periwinkle
        salmon: "#FF7A6B", // Salmon
        alice: "#F2F9FF", // Alice Blue
        surface: "#1C1938",
        surface2: "#262249",
        line: "#322D5E",
        muted: "#A19DC4",
      },
      fontFamily: {
        display: ["Sora", "Inter", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 4px rgba(102,197,255,.15)",
        card: "0 10px 30px -12px rgba(0,0,0,.6)",
      },
    },
  },
  plugins: [],
};

module.exports = {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: { 
	keyframes: {
    spinReverse: { to: { transform: 'rotate(-360deg)' } }
  },
  animation: {
    'spin-slow':            'spin 120s linear infinite',
    'spin-slow-reverse':    'spinReverse 120s linear infinite',
    'spin-inner':           'spin 45s linear infinite',
    'spin-inner-reverse':   'spinReverse 120s linear infinite',
  },
fontFamily: {
        merienda: ['"Merienda"', 'cursive'],
        lato: ['"Lato"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

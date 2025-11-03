import type { Config } from "tailwindcss";

// Configuración de Tailwind CSS para Lune CD v3.0
// Con colores personalizados y animaciones increíbles
const config: Config = {
    darkMode: "class",
    content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
        extend: {
                // Paleta de colores personalizada para Lune CD
                colors: {
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                        card: {
                                DEFAULT: 'hsl(var(--card))',
                                foreground: 'hsl(var(--card-foreground))'
                        },
                        popover: {
                                DEFAULT: 'hsl(var(--popover))',
                                foreground: 'hsl(var(--popover-foreground))'
                        },
                        primary: {
                                DEFAULT: 'hsl(var(--primary))',
                                foreground: 'hsl(var(--primary-foreground))'
                        },
                        secondary: {
                                DEFAULT: 'hsl(var(--secondary))',
                                foreground: 'hsl(var(--secondary-foreground))'
                        },
                        muted: {
                                DEFAULT: 'hsl(var(--muted))',
                                foreground: 'hsl(var(--muted-foreground))'
                        },
                        accent: {
                                DEFAULT: 'hsl(var(--accent))',
                                foreground: 'hsl(var(--accent-foreground))'
                        },
                        destructive: {
                                DEFAULT: 'hsl(var(--destructive))',
                                foreground: 'hsl(var(--destructive-foreground))'
                        },
                        border: 'hsl(var(--border))',
                        input: 'hsl(var(--input))',
                        ring: 'hsl(var(--ring))',
                        chart: {
                                '1': 'hsl(var(--chart-1))',
                                '2': 'hsl(var(--chart-2))',
                                '3': 'hsl(var(--chart-3))',
                                '4': 'hsl(var(--chart-4))',
                                '5': 'hsl(var(--chart-5))'
                        },
                        // Colores adicionales para Lune CD
                        lune: {
                                primary: '#667eea',
                                secondary: '#764ba2',
                                accent: '#ff69b4',
                                dark: '#0f172a',
                                light: '#f8fafc'
                        }
                },
                // Bordes redondeados personalizados
                borderRadius: {
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)',
                        'lune': '20px', // Bordes redondeados de Lune
                        'button': '50px', // Botones redondos del menú
                        'message': '18px' // Mensajes del chat
                },
                // Animaciones personalizadas
                keyframes: {
                        'bounce-gentle': {
                                '0%, 20%, 50%, 80%, 100%': { transform: 'translateY(0)' },
                                '40%': { transform: 'translateY(-15px)' },
                                '60%': { transform: 'translateY(-8px)' }
                        },
                        'glow-pulse': {
                                '0%': { textShadow: '0 0 20px rgba(255, 255, 255, 0.5)' },
                                '50%': { textShadow: '0 0 30px rgba(255, 255, 255, 0.8), 0 0 40px rgba(255, 255, 255, 0.6)' },
                                '100%': { textShadow: '0 0 20px rgba(255, 255, 255, 0.5)' }
                        },
                        'float-animation': {
                                '0%, 100%': { transform: 'translateY(0px)' },
                                '50%': { transform: 'translateY(-20px)' }
                        },
                        'message-slide': {
                                '0%': { opacity: '0', transform: 'translateY(20px)' },
                                '100%': { opacity: '1', transform: 'translateY(0)' }
                        },
                        'typing-dot': {
                                '0%, 80%, 100%': { transform: 'scale(0.8)', opacity: '0.5' },
                                '40%': { transform: 'scale(1)', opacity: '1' }
                        },
                        'shimmer': {
                                '0%': { transform: 'translateX(-100%)' },
                                '100%': { transform: 'translateX(100%)' }
                        },
                        'particle-fly': {
                                '0%': { opacity: '1', transform: 'translate(0, 0) scale(1)' },
                                '100%': { opacity: '0', transform: 'translate(var(--x), var(--y)) scale(0.3)' }
                        }
                },
                animation: {
                        'bounce-gentle': 'bounce-gentle 2s infinite',
                        'glow-pulse': 'glow-pulse 2s ease-in-out infinite alternate',
                        'float': 'float-animation 6s ease-in-out infinite',
                        'message-slide': 'message-slide 0.3s ease-out',
                        'typing': 'typing-dot 1.4s infinite ease-in-out',
                        'shimmer': 'shimmer 2s infinite',
                        'particle': 'particle-fly 1.5s ease-out forwards'
                },
                // Sombras personalizadas
                boxShadow: {
                        'lune': '0 15px 40px rgba(102, 126, 234, 0.6)',
                        'lune-hover': '0 10px 30px rgba(0, 0, 0, 0.3)',
                        'button': '0 5px 15px rgba(102, 126, 234, 0.4)',
                        'glow': '0 0 30px rgba(255, 255, 255, 0.8)',
                        'message': '0 2px 4px rgba(0, 0, 0, 0.2)'
                },
                // Gradientes personalizados
                backgroundImage: {
                        'lune-gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        'button-gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        'glass': 'rgba(255, 255, 255, 0.1)',
                        'glass-dark': 'rgba(15, 23, 42, 0.95)'
                },
                // Backdrop filters para efectos de cristal
                backdropBlur: {
                        'lune': '10px'
                }
        }
  },
  plugins: [],
};
export default config;
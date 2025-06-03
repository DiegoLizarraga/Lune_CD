import pygame
import sys
import os

# Inicializar Pygame
pygame.init()

# Obtener información de la pantalla
info = pygame.display.Info()
ANCHO_PANTALLA, ALTO_PANTALLA = info.current_w, info.current_h

# Tamaño de la ventana de la mascota
ANCHO_VENTANA = 170
ALTO_VENTANA = 170

# Posición en esquina inferior izquierda
pos_ventana_x = 20
pos_ventana_y = ALTO_PANTALLA - ALTO_VENTANA - 60  # 60px desde el borde inferior

# Configurar la posición de la ventana antes de crearla
os.environ['SDL_VIDEO_WINDOW_POS'] = f'{pos_ventana_x},{pos_ventana_y}'

# Crear ventana sin bordes y con transparencia
ventana = pygame.display.set_mode((ANCHO_VENTANA, ALTO_VENTANA), pygame.NOFRAME)
pygame.display.set_caption("Lune - Mascota Virtual")

# Configurar transparencia de ventana (Windows)
try:
    import ctypes
    from ctypes import wintypes
    
    # Obtener handle de la ventana
    hwnd = pygame.display.get_wm_info()["window"]
    
    # Hacer la ventana "always on top"
    ctypes.windll.user32.SetWindowPos(hwnd, -1, pos_ventana_x, pos_ventana_y, 0, 0, 0x0001)
    
    # Configurar transparencia
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, 0x00080000 | 0x00000020)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x000000, 255, 0x00000002)
except:
    print("No se pudo configurar transparencia (probablemente no estás en Windows)")

# Rutas de imágenes
carpeta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_normal = os.path.join(carpeta_actual, "Lune_normal.png")
ruta_feliz = os.path.join(carpeta_actual, "Lune_feliz.png")

# Crear imagen normal si no existe
if not os.path.exists(ruta_normal):
    superficie = pygame.Surface((150, 150), pygame.SRCALPHA)
    # Cabeza
    pygame.draw.circle(superficie, (255, 200, 150), (75, 75), 70)
    # Ojos
    pygame.draw.circle(superficie, (50, 50, 50), (55, 60), 8)
    pygame.draw.circle(superficie, (50, 50, 50), (95, 60), 8)
    # Boca neutral
    pygame.draw.arc(superficie, (50, 50, 50), (60, 85, 30, 20), 0, 3.14, 3)
    # Mejillas
    pygame.draw.circle(superficie, (255, 180, 120), (40, 80), 12)
    pygame.draw.circle(superficie, (255, 180, 120), (110, 80), 12)
    pygame.image.save(superficie, ruta_normal)

# Crear imagen feliz si no existe
if not os.path.exists(ruta_feliz):
    superficie = pygame.Surface((150, 150), pygame.SRCALPHA)
    # Cabeza más brillante
    pygame.draw.circle(superficie, (255, 220, 180), (75, 75), 70)
    # Ojos cerrados (feliz)
    pygame.draw.arc(superficie, (30, 30, 30), (45, 55, 20, 15), 0, 3.14, 4)
    pygame.draw.arc(superficie, (30, 30, 30), (85, 55, 20, 15), 0, 3.14, 4)
    # Sonrisa grande
    pygame.draw.arc(superficie, (30, 30, 30), (45, 80, 60, 35), 0, 3.14, 4)
    # Mejillas rosadas
    pygame.draw.circle(superficie, (255, 150, 150), (40, 80), 15)
    pygame.draw.circle(superficie, (255, 150, 150), (110, 80), 15)
    # Efecto de brillo
    pygame.draw.circle(superficie, (255, 255, 255, 100), (65, 50), 8)
    pygame.image.save(superficie, ruta_feliz)

# Función para ajustar imagen al tamaño de ventana
def ajustar_imagen(imagen, ancho_ventana, alto_ventana):
    # Obtener dimensiones originales
    ancho_original = imagen.get_width()
    alto_original = imagen.get_height()
    
    # Calcular el ratio para mantener la proporción
    ratio_ancho = (ancho_ventana - 20) / ancho_original  # 20px de margen total
    ratio_alto = (alto_ventana - 20) / alto_original     # 20px de margen total
    
    # Usar el ratio menor para que la imagen quepa completamente
    ratio = min(ratio_ancho, ratio_alto)
    
    # Calcular nuevas dimensiones
    nuevo_ancho = int(ancho_original * ratio)
    nuevo_alto = int(alto_original * ratio)
    
    # Redimensionar imagen
    imagen_ajustada = pygame.transform.scale(imagen, (nuevo_ancho, nuevo_alto))
    
    return imagen_ajustada, nuevo_ancho, nuevo_alto

# Cargar imágenes
try:
    lune_normal_original = pygame.image.load(ruta_normal).convert_alpha()
    lune_feliz_original = pygame.image.load(ruta_feliz).convert_alpha()
    
    # Ajustar imágenes al tamaño de la ventana
    lune_normal, ancho_img, alto_img = ajustar_imagen(lune_normal_original, ANCHO_VENTANA, ALTO_VENTANA)
    lune_feliz, _, _ = ajustar_imagen(lune_feliz_original, ANCHO_VENTANA, ALTO_VENTANA)
    
    print(f"Imágenes cargadas y ajustadas a {ancho_img}x{alto_img}")
    
except:
    print("Error al cargar las imágenes")
    pygame.quit()
    sys.exit()

# Variables de estado
estado_actual = lune_normal
tiempo_reaccion = 0
arrastrar = False
offset_x = 0
offset_y = 0

# Color de transparencia (magenta)
COLOR_TRANSPARENTE = (255, 0, 255)

print("Mascota Lune iniciada!")
print("- Haz clic en Lune para hacerla feliz")
print("- Arrastra para mover la mascota")
print("- Presiona Ctrl+N para hacerla feliz")
print("- Presiona Ctrl+Q para cerrar (ÚNICA forma de cerrar)")
print("- La ventana NO se puede cerrar con la X")
print("- Los mensajes de debug aparecerán en la consola")

# Bucle principal
reloj = pygame.time.Clock()
ejecutando = True

while ejecutando:
    for evento in pygame.event.get():
        # Solo cerrar con Ctrl+Q, ignorar otros eventos de cierre
        if evento.type == pygame.QUIT:
            continue  # Ignorar el evento de cierre de ventana
        
        # Manejo de teclas
        if evento.type == pygame.KEYDOWN:
            teclas = pygame.key.get_pressed()
            mods = pygame.key.get_mods()
            
            # Cerrar SOLO con Ctrl + Q
            if teclas[pygame.K_q] and (mods & pygame.KMOD_CTRL):
                ejecutando = False
                break
            
            # Cambiar a imagen feliz con Ctrl + N
            if teclas[pygame.K_n] and (mods & pygame.KMOD_CTRL):
                estado_actual = lune_feliz
                tiempo_reaccion = pygame.time.get_ticks() + 2000  # 2 segundos
        
        # Manejo del mouse
        if evento.type == pygame.MOUSEBUTTONDOWN:
            if evento.button == 1:  # Solo clic izquierdo
                mouse_x, mouse_y = pygame.mouse.get_pos()
                print(f"Clic detectado en: ({mouse_x}, {mouse_y})")  # Debug
                
                # Calcular posición centrada de la imagen
                pos_img_x = (ANCHO_VENTANA - ancho_img) // 2
                pos_img_y = (ALTO_VENTANA - alto_img) // 2
                print(f"Área de imagen: x={pos_img_x}-{pos_img_x + ancho_img}, y={pos_img_y}-{pos_img_y + alto_img}")  # Debug
                
                # Verificar si el clic está dentro de la imagen (área más permisiva)
                margen = 15  # Área extra alrededor de la imagen
                if (pos_img_x - margen <= mouse_x <= pos_img_x + ancho_img + margen) and \
                   (pos_img_y - margen <= mouse_y <= pos_img_y + alto_img + margen):
                    print("¡Clic en la mascota detectado!")  # Debug
                    estado_actual = lune_feliz
                    tiempo_reaccion = pygame.time.get_ticks() + 2000  # 2 segundos
                
                # Iniciar arrastrar
                arrastrar = True
                offset_x = mouse_x
                offset_y = mouse_y
        
        if evento.type == pygame.MOUSEBUTTONUP:
            if evento.button == 1:  # Solo clic izquierdo
                arrastrar = False
        
        if evento.type == pygame.MOUSEMOTION and arrastrar:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            nueva_pos_x = pos_ventana_x + (mouse_x - offset_x)
            nueva_pos_y = pos_ventana_y + (mouse_y - offset_y)
            
            # Limitar movimiento dentro de la pantalla
            nueva_pos_x = max(0, min(nueva_pos_x, ANCHO_PANTALLA - ANCHO_VENTANA))
            nueva_pos_y = max(0, min(nueva_pos_y, ALTO_PANTALLA - ALTO_VENTANA))
            
            # Mover ventana (solo funciona en algunos sistemas)
            try:
                os.environ['SDL_VIDEO_WINDOW_POS'] = f'{nueva_pos_x},{nueva_pos_y}'
                pos_ventana_x = nueva_pos_x
                pos_ventana_y = nueva_pos_y
            except:
                pass

    # Volver al estado normal después de la reacción
    if tiempo_reaccion and pygame.time.get_ticks() > tiempo_reaccion:
        estado_actual = lune_normal
        tiempo_reaccion = 0

    # Limpiar pantalla con color transparente
    ventana.fill(COLOR_TRANSPARENTE)
    
    # Calcular posición centrada para la imagen
    pos_x_centrada = (ANCHO_VENTANA - ancho_img) // 2
    pos_y_centrada = (ALTO_VENTANA - alto_img) // 2
    
    # Dibujar la mascota centrada en la ventana
    ventana.blit(estado_actual, (pos_x_centrada, pos_y_centrada))
    
    # Actualizar pantalla
    pygame.display.flip()
    reloj.tick(60)

print("¡Hasta luego!")
pygame.quit()
sys.exit()
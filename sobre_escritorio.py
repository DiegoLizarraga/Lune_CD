import pygame
import sys

# Inicializar Pygame
pygame.init()

# Configuración de la ventana (transparente y sin bordes)
width, height = 200, 200
screen = pygame.display.set_mode((width, height), pygame.NOFRAME)
pygame.display.set_caption("Prueba Mascota Lune_CD")

# Color de fondo transparente
transparent = (0, 0, 0, 0)
screen.fill(transparent)

# Cargar imagen de la mascota (o crear una placeholder)
try:
    mascota_img = pygame.image.load("Lune.png").convert_alpha()
except:
    mascota_img = pygame.Surface((100, 100), pygame.SRCALPHA)
    pygame.draw.circle(mascota_img, (255, 200, 150), (50, 50), 50)  # Cabeza
    pygame.draw.circle(mascota_img, (0, 0, 0), (35, 35), 8)         # Ojo izquierdo
    pygame.draw.circle(mascota_img, (0, 0, 0), (65, 35), 8)         # Ojo derecho
    pygame.draw.arc(mascota_img, (0, 0, 0), (30, 50, 40, 20), 0, 3.14, 3)  # Sonrisa

# Posición inicial
x, y = 100, 100

# Bucle principal
clock = pygame.time.Clock()
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        # Cerrar con Ctrl + P
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p and pygame.key.get_mods() & pygame.KMOD_CTRL:
                running = False
    
    # Seguir el cursor del mouse (con suavizado)
    mouse_x, mouse_y = pygame.mouse.get_pos()
    x += (mouse_x - x - 50) * 0.1
    y += (mouse_y - y - 50) * 0.1
    
    # Dibujar
    screen.fill(transparent)
    screen.blit(mascota_img, (x, y))
    pygame.display.flip()
    clock.tick(60)

# Salir
pygame.quit()
sys.exit()
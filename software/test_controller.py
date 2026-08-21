import pygame

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("No controller found!")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()

print(f"Controller: {joystick.get_name()}")
print("Moving joysticks will show values...")
print("Press A button to exit")

running = True
while running:
    pygame.event.pump()
    
    # Axes
    axes = [joystick.get_axis(i) for i in range(5)]
    print(f"L:X {axes[0]:5.2f} L:Y {axes[1]:5.2f} R:X {axes[3]:5.2f} R:Y {axes[4]:5.2f}", end='\r')
    
    # Buttons
    if joystick.get_button(0):  # A button
        running = False

pygame.quit()
print("\nTest complete!")

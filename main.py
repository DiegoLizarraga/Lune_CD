# Chatbot básico en Python

def chatbot():
    print("Hola, soy tu asistente virtual. Escribe 'salir' para terminar.\n")

    while True:
        user_input = input("Tú: ").lower()

        if user_input == "salir":
            print("Bot: ¡Hasta luego!")
            break
        elif "hola" in user_input:
            print("Bot: ¡Hola! ¿En qué puedo ayudarte?")
        elif "cómo estás" in user_input:
            print("Bot: Estoy bien, gracias. ¿Y tú?")
        elif "tu nombre" in user_input:
            print("Bot: Me puedes llamar AsistBot.")
        elif "gracias" in user_input:
            print("Bot: ¡De nada!")
        else:
            print("Bot: Lo siento, no entiendo lo que dices.")

# Ejecutar el chatbot
chatbot()

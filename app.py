from flask import Flask, request, jsonify
import requests
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde un archivo .env (para desarrollo)
load_dotenv()

# Configuración básica de la aplicación
app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
HUGGINGFACE_API_URL = os.environ.get('HUGGINGFACE_API_URL')
HUGGINGFACE_TOKEN = os.environ.get('HUGGINGFACE_TOKEN')

# Validar que las variables de entorno estén configuradas
if not all([PAGE_ACCESS_TOKEN, HUGGINGFACE_API_URL]):
    raise ValueError("Faltan variables de entorno requeridas.")

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """
    Verifica el webhook de Facebook Messenger.
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == os.environ.get('VERIFY_TOKEN'):
        logger.info("Webhook verificado exitosamente.")
        return challenge, 200
    logger.error("Error en la verificación del webhook.")
    return 'Error', 403

@app.route('/webhook', methods=['POST'])
def handle_messages():
    """
    Maneja los mensajes entrantes de Facebook Messenger.
    """
    try:
        data = request.json
        if data.get('object') == 'page':
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    sender_id = messaging_event.get('sender', {}).get('id')
                    message_text = messaging_event.get('message', {}).get('text')

                    if not sender_id or not message_text:
                        logger.warning("Mensaje incompleto recibido.")
                        continue

                    # Validar y sanitizar la entrada del usuario
                    if not isinstance(message_text, str) or len(message_text) > 500:
                        logger.warning("Entrada de usuario no válida.")
                        send_message(sender_id, "Lo siento, no puedo procesar tu mensaje.")
                        continue

                    # Llamar a la API de Hugging Face
                    headers = {'Authorization': f'Bearer {HUGGINGFACE_TOKEN}'} if HUGGINGFACE_TOKEN else {}
                    try:
                        response = requests.post(
                            HUGGINGFACE_API_URL,
                            json={'inputs': message_text},
                            headers=headers,
                            timeout=10  # Limitar el tiempo de espera
                        )
                        response.raise_for_status()  # Lanza una excepción para respuestas no exitosas
                        chatbot_response = response.json()[0].get('generated_text', 'Lo siento, no pude generar una respuesta.')
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Error al llamar a la API de Hugging Face: {e}")
                        chatbot_response = "Lo siento, hubo un error al procesar tu mensaje."

                    # Enviar la respuesta a Facebook Messenger
                    send_message(sender_id, chatbot_response)
        return 'OK', 200
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return 'Error', 500

def send_message(recipient_id, message_text):
    """
    Envía un mensaje a través de Facebook Messenger.
    """
    try:
        params = {'access_token': PAGE_ACCESS_TOKEN}
        headers = {'Content-Type': 'application/json'}
        data = {
            'recipient': {'id': recipient_id},
            'message': {'text': message_text}
        }
        response = requests.post(
            'https://graph.facebook.com/v12.0/me/messages',
            params=params,
            headers=headers,
            json=data,
            timeout=10  # Limitar el tiempo de espera
        )
        response.raise_for_status()
        logger.info(f"Mensaje enviado a {recipient_id}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al enviar mensaje a {recipient_id}: {e}")

# Punto de entrada para Vercel
def vercel_handler(request):
    from flask import Response
    with app.app_context():
        response = app.full_dispatch_request()
        return Response(response=response.get_data(), status=response.status_code, headers=dict(response.headers))

if __name__ == '__main__':
    app.run(debug=os.environ.get('DEBUG', 'False').lower() == 'true')

import re
from datetime import datetime, timedelta

class CommandProcessor:
    def __init__(self, system_integration, chatbot):
        self.system_integration = system_integration
        self.chatbot = chatbot
        
    def process_command(self, message):
        """Procesa un comando del usuario"""
        message_lower = message.lower()
        
        # Comandos para abrir aplicaciones
        if self._is_open_app_command(message_lower):
            app_name = self._extract_app_name(message)
            return self.system_integration.open_application(app_name)
        
        # Comandos para notas
        if self._is_note_command(message_lower):
            return self._process_note_command(message)
        
        # Comandos para recordatorios
        if self._is_reminder_command(message_lower):
            return self._process_reminder_command(message)
        
        # Comandos para buscar en historial de pantalla
        if self._is_screen_search_command(message_lower):
            query = self._extract_search_query(message)
            return self.system_integration.search_screen_history(query)
        
        # Comandos para información del sistema
        if self._is_system_info_command(message_lower):
            return self._get_system_info()
        
        # Si no es un comando reconocido, pasar al chatbot
        return None
    
    def _is_open_app_command(self, message):
        patterns = [
            r'abre\s+(.+)',
            r'inicia\s+(.+)',
            r'ejecuta\s+(.+)',
            r'abrir\s+(.+)',
            r'iniciar\s+(.+)',
            r'ejecutar\s+(.+)'
        ]
        
        for pattern in patterns:
            if re.match(pattern, message):
                return True
        return False
    
    def _extract_app_name(self, message):
        patterns = [
            r'abre\s+(.+)',
            r'inicia\s+(.+)',
            r'ejecuta\s+(.+)',
            r'abrir\s+(.+)',
            r'iniciar\s+(.+)',
            r'ejecutar\s+(.+)'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, message)
            if match:
                return match.group(1).strip()
        return ""
    
    def _is_note_command(self, message):
        patterns = [
            r'toma\s+nota\s+(.+)',
            r'guarda\s+nota\s+(.+)',
            r'anota\s+(.+)',
            r'nota\s+(.+)',
            r'recuerda\s+que\s+(.+)'
        ]
        
        for pattern in patterns:
            if re.match(pattern, message):
                return True
        return False
    
    def _process_note_command(self, message):
        patterns = [
            (r'toma\s+nota\s+(.+)', lambda m: (m.group(1), m.group(1))),
            (r'guarda\s+nota\s+(.+)', lambda m: (m.group(1), m.group(1))),
            (r'anota\s+(.+)', lambda m: (m.group(1), m.group(1))),
            (r'nota\s+(.+)', lambda m: (m.group(1), m.group(1))),
            (r'recuerda\s+que\s+(.+)', lambda m: (f"Recordatorio: {m.group(1)}", m.group(1)))
        ]
        
        for pattern, extractor in patterns:
            match = re.match(pattern, message)
            if match:
                title, content = extractor(match)
                return self.system_integration.add_note(title, content)
        
        # Comando para listar notas
        if "lista mis notas" in message or "muestrame mis notas" in message:
            return self.system_integration.list_notes()
        
        # Comando para obtener una nota específica
        note_match = re.match(r'busca\s+nota\s+(.+)|muestra\s+nota\s+(.+)|dime\s+nota\s+(.+)', message)
        if note_match:
            title = next((group for group in note_match.groups() if group), "")
            return self.system_integration.get_note(title)
        
        return "No entendí el comando de nota. ¿Podrías ser más específico?"
    
    def _is_reminder_command(self, message):
        patterns = [
            r'recuérdame\s+(.+)\s+(a\s+las\s+|en\s+|para\s+)(.+)',
            r'avisame\s+(.+)\s+(a\s+las\s+|en\s+|para\s+)(.+)',
            r'recordatorio\s+(.+)\s+(a\s+las\s+|en\s+|para\s+)(.+)'
        ]
        
        for pattern in patterns:
            if re.match(pattern, message):
                return True
        return False
    
    def _process_reminder_command(self, message):
        patterns = [
            r'recuérdame\s+(.+)\s+(a\s+las\s+|en\s+|para\s+)(.+)',
            r'avisame\s+(.+)\s+(a\s+las\s+|en\s+|para\s+)(.+)',
            r'recordatorio\s+(.+)\s+(a\s+las\s+|en\s+|para\s+)(.+)'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, message)
            if match:
                task = match.group(1)
                time_expr = match.group(3)
                
                # Procesar la expresión de tiempo
                reminder_time = self._parse_time_expression(time_expr)
                if reminder_time:
                    return self.system_integration.add_reminder(task, reminder_time)
                else:
                    return f"No entendí cuándo quieres que te recuerde '{task}'. Intenta con 'a las 18:00' o 'en 30 minutos'."
        
        return "No entendí el comando de recordatorio. ¿Podrías ser más específico?"
    
    def _parse_time_expression(self, time_expr):
        """Parsea una expresión de tiempo y devuelve una cadena de tiempo formateada"""
        now = datetime.now()
        
        # Formato "a las HH:MM"
        time_match = re.match(r'a\s+las\s+(\d{1,2}):(\d{2})', time_expr)
        if time_match:
            hour, minute = int(time_match.group(1)), int(time_match.group(2))
            reminder_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Si la hora ya pasó, programar para mañana
            if reminder_date <= now:
                reminder_date += timedelta(days=1)
                
            return reminder_date.strftime("%Y-%m-%d %H:%M")
        
        # Formato "en X minutos/horas"
        rel_time_match = re.match(r'en\s+(\d+)\s+(minutos?|horas?)', time_expr)
        if rel_time_match:
            amount = int(rel_time_match.group(1))
            unit = rel_time_match.group(2)
            
            if "minuto" in unit:
                reminder_date = now + timedelta(minutes=amount)
            else:  # horas
                reminder_date = now + timedelta(hours=amount)
                
            return reminder_date.strftime("%Y-%m-%d %H:%M")
        
        # Formato "mañana a las HH:MM"
        tomorrow_match = re.match(r'mañana\s+a\s+las\s+(\d{1,2}):(\d{2})', time_expr)
        if tomorrow_match:
            hour, minute = int(tomorrow_match.group(1)), int(tomorrow_match.group(2))
            reminder_date = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            return reminder_date.strftime("%Y-%m-%d %H:%M")
        
        return None
    
    def _is_screen_search_command(self, message):
        patterns = [
            r'busca\s+en\s+pantalla\s+(.+)',
            r'qué\s+viste\s+en\s+pantalla\s+sobre\s+(.+)',
            r'recuerdas\s+algo\s+sobre\s+(.+)\s+en\s+pantalla'
        ]
        
        for pattern in patterns:
            if re.match(pattern, message):
                return True
        return False
    
    def _extract_search_query(self, message):
        patterns = [
            r'busca\s+en\s+pantalla\s+(.+)',
            r'qué\s+viste\s+en\s+pantalla\s+sobre\s+(.+)',
            r'recuerdas\s+algo\s+sobre\s+(.+)\s+en\s+pantalla'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, message)
            if match:
                return match.group(1).strip()
        return ""
    
    def _is_system_info_command(self, message):
        keywords = ['información del sistema', 'info sistema', 'datos del sistema', 'sistema operativo']
        return any(keyword in message for keyword in keywords)
    
    def _get_system_info(self):
        import platform
        import psutil
        
        try:
            info = {
                "Sistema Operativo": platform.system(),
                "Versión": platform.version(),
                "Procesador": platform.processor(),
                "CPU (%)": f"{psutil.cpu_percent()}%",
                "Memoria RAM": f"{psutil.virtual_memory().percent}% en uso",
                "Disco Duro": f"{psutil.disk_usage('/').percent}% en uso"
            }
            
            response = "Información del sistema:\n"
            for key, value in info.items():
                response += f"- {key}: {value}\n"
                
            return response
        except Exception as e:
            return f"No pude obtener la información del sistema: {str(e)}"

import re
from collections import Counter
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# Descargar recursos necesarios de NLTK (solo la primera vez)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

class ScreenAnalyzer:
    def __init__(self):
        self.stop_words = set(stopwords.words('spanish'))
        self.important_keywords = self._load_important_keywords()
        self.context_history = []
        
    def _load_important_keywords(self):
        """Carga una lista de palabras clave importantes para el seguimiento"""
        return [
            "tarea", "proyecto", "reunión", "fecha límite", "deadline", "entrega",
            "examen", "estudio", "trabajo", "oferta", "empleo", "vacante",
            "compra", "venta", "oferta", "descuento", "promoción",
            "cita", "evento", "conferencia", "webinar", "presentación",
            "recordatorio", "agenda", "calendario", "cumpleaños", "aniversario"
        ]
    
    def analyze_text(self, text):
        """Analiza el texto de la pantalla y extrae información relevante"""
        # Tokenizar y limpiar el texto
        words = word_tokenize(text.lower())
        words = [word for word in words if word.isalpha() and word not in self.stop_words]
        
        # Extraer entidades y patrones importantes
        dates = self._extract_dates(text)
        times = self._extract_times(text)
        emails = self._extract_emails(text)
        phone_numbers = self._extract_phone_numbers(text)
        urls = self._extract_urls(text)
        
        # Encontrar palabras clave importantes
        important_found = [word for word in words if word in self.important_keywords]
        
        # Contar frecuencia de palabras (excluyendo stopwords)
        word_freq = Counter(words)
        common_words = word_freq.most_common(10)
        
        # Crear resumen del análisis
        analysis = {
            "important_keywords": important_found,
            "dates": dates,
            "times": times,
            "emails": emails,
            "phone_numbers": phone_numbers,
            "urls": urls,
            "common_words": common_words,
            "text_length": len(text),
            "word_count": len(words)
        }
        
        # Guardar en historial de contexto
        self.context_history.append(analysis)
        
        # Mantener solo los últimos 20 análisis
        if len(self.context_history) > 20:
            self.context_history.pop(0)
        
        return analysis
    
    def _extract_dates(self, text):
        """Extrae fechas del texto"""
        date_patterns = [
            r'\b\d{1,2}\/\d{1,2}\/\d{2,4}\b',  # DD/MM/YYYY
            r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',    # DD-MM-YYYY
            r'\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b',  # DD de Mes de YYYY
            r'\b\w+\s+\d{1,2},\s+\d{4}\b'      # Mes DD, YYYY
        ]
        
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            dates.extend(matches)
        
        return dates
    
    def _extract_times(self, text):
        """Extrae horas del texto"""
        time_patterns = [
            r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b',  # HH:MM AM/PM
            r'\b\d{1,2}\s*(?:AM|PM|am|pm)\b'           # HH AM/PM
        ]
        
        times = []
        for pattern in time_patterns:
            matches = re.findall(pattern, text)
            times.extend(matches)
        
        return times
    
    def _extract_emails(self, text):
        """Extrae direcciones de correo electrónico"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return re.findall(email_pattern, text)
    
    def _extract_phone_numbers(self, text):
        """Extrae números de teléfono"""
        phone_patterns = [
            r'\b\d{3}-\d{3}-\d{4}\b',        # XXX-XXX-XXXX
            r'\b\(\d{3}\)\s*\d{3}-\d{4}\b',  # (XXX) XXX-XXXX
            r'\b\d{10}\b'                    # XXXXXXXXXX
        ]
        
        phones = []
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)
        
        return phones
    
    def _extract_urls(self, text):
        """Extrae URLs del texto"""
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        return re.findall(url_pattern, text)
    
    def get_context_summary(self):
        """Genera un resumen del contexto actual basado en el historial"""
        if not self.context_history:
            return "No hay información de contexto disponible."
        
        # Recopilar todas las palabras clave importantes
        all_keywords = []
        for analysis in self.context_history:
            all_keywords.extend(analysis["important_keywords"])
        
        # Contar frecuencia de palabras clave
        keyword_freq = Counter(all_keywords)
        top_keywords = keyword_freq.most_common(5)
        
        # Recopilar todas las fechas y horas
        all_dates = []
        all_times = []
        for analysis in self.context_history:
            all_dates.extend(analysis["dates"])
            all_times.extend(analysis["times"])
        
        # Crear resumen
        summary = "Resumen de contexto:\n"
        
        if top_keywords:
            summary += "Temas importantes: " + ", ".join([f"{word} ({count})" for word, count in top_keywords]) + "\n"
        
        if all_dates:
            unique_dates = list(set(all_dates))
            summary += f"Fechas mencionadas: {', '.join(unique_dates)}\n"
        
        if all_times:
            unique_times = list(set(all_times))
            summary += f"Horas mencionadas: {', '.join(unique_times)}\n"
        
        return summary
    
    def search_context(self, query):
        """Busca en el historial de contexto"""
        query_lower = query.lower()
        results = []
        
        for i, analysis in enumerate(self.context_history):
            # Buscar en palabras clave
            for keyword in analysis["important_keywords"]:
                if query_lower in keyword:
                    results.append({
                        "index": i,
                        "match_type": "keyword",
                        "match": keyword
                    })
            
            # Buscar en palabras comunes
            for word, count in analysis["common_words"]:
                if query_lower in word:
                    results.append({
                        "index": i,
                        "match_type": "word",
                        "match": f"{word} ({count} veces)"
                    })
        
        if results:
            response = f"Encontré {len(results)} coincidencias con '{query}':\n"
            for result in results:
                response += f"- Análisis #{result['index']}: {result['match_type']} - {result['match']}\n"
            return response
        else:
            return f"No encontré información sobre '{query}' en el contexto reciente."
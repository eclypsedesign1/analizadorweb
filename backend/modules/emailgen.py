import anthropic
from backend.config import ANTHROPIC_API_KEY
from backend.models import AnalysisResult


def generate_email(result: AnalysisResult, product: str = "mantenimiento-web") -> str:
    if not ANTHROPIC_API_KEY:
        return ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    issues_text = ""
    if result.score and result.score.top_issues:
        issues_text = "\n".join(
            f"- {i.message}" + (f": {i.detail}" if i.detail else "")
            for i in result.score.top_issues[:5]
        )

    contact_name = (result.contacts.contact_name if result.contacts else None) or result.name or ""
    email_dest = (result.contacts.emails[0] if result.contacts and result.contacts.emails else None) or result.email or ""

    prompt = f"""Eres el equipo de ventas de Eclypse, una agencia de desarrollo web especializada en WordPress, performance y seguridad.

Analizaste el sitio web {result.domain} y encontraste los siguientes problemas:
{issues_text if issues_text else "Sin problemas críticos detectados."}

Score comercial: {result.score.total if result.score else "N/A"}/100 ({result.score.label if result.score else ""})
CMS: {result.cms.cms if result.cms else "Desconocido"} {result.cms.version or "" if result.cms else ""}
{"Nombre del contacto: " + contact_name if contact_name else ""}

Escribe un email de prospección comercial en español para ofrecerles los servicios de Eclypse.
El email debe:
1. Ser breve (máximo 120 palabras)
2. Mencionar 2-3 problemas específicos encontrados en su sitio
3. Proponer concretamente cómo Eclypse los resuelve
4. Tener un CTA claro (agendar una llamada o responder el email)
5. Tono profesional pero cercano, sin ser invasivo
6. NO usar frases genéricas como "espero que te encuentres bien"

Formato:
Asunto: [asunto del email]

[cuerpo del email]

Firma:
Equipo Eclypse
contacto@eclypsedesign.com
eclypsedesign.com"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text if message.content else ""

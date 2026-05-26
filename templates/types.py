from fastapi.templating import Jinja2Templates
from starlette_async_jinja import AsyncJinja2Templates

type TemplateEngine = Jinja2Templates | AsyncJinja2Templates

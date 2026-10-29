from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Obligatoria desde .env, como secret_key: no se guardan credenciales en el código.
    database_url: str
    secret_key: str
    # Secreto de los seudónimos estables (registros de privacidad, exportaciones de
    # investigación). Si falta, se usa secret_key; conviene fijarlo aparte para poder
    # rotar secret_key sin cambiar los seudónimos ya registrados.
    seudonimo_secreto: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    access_token_expire_minutes: int = 10080
    allowed_origins: str = "https://rizoma.entornodepruebas.com.ar,https://kanban.entornodepruebas.com.ar,https://desarrollo3.entornodepruebas.com.ar"
    allowed_hosts: str = "rizoma.entornodepruebas.com.ar,kanban.entornodepruebas.com.ar,desarrollo3.entornodepruebas.com.ar,66.97.41.23,127.0.0.1,localhost"
    initial_admin_password: str = ""
    environment: str = "production"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    class Config:
        env_file = ".env"


settings = Settings()

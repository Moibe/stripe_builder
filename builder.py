import os
import stripe
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()


class StripeClient:
    """Cliente para conectarse a Stripe con soporte para múltiples ambientes."""
    
    def __init__(self, environment: str = None):
        """
        Inicializa el cliente de Stripe.
        
        Args:
            environment: 'sandbox' o 'prod'. Si no se especifica, usa STRIPE_ENV del .env
        """
        # Usar ambiente especificado o el del archivo .env
        self.environment = environment or os.getenv('STRIPE_ENV', 'sandbox')
        
        if self.environment not in ['sandbox', 'prod']:
            raise ValueError(f"Ambiente inválido: {self.environment}. Debe ser 'sandbox' o 'prod'")
        
        # Cargar la clave secreta según el ambiente
        if self.environment == 'sandbox':
            self.api_key = os.getenv('STRIPE_SANDBOX_SECRET_KEY')
            self.publishable_key = os.getenv('STRIPE_SANDBOX_PUBLISHABLE_KEY')
        else:
            self.api_key = os.getenv('STRIPE_PROD_SECRET_KEY')
            self.publishable_key = os.getenv('STRIPE_PROD_PUBLISHABLE_KEY')
        
        # Validar que las claves existan
        if not self.api_key:
            raise ValueError(f"No se encontró STRIPE_{self.environment.upper()}_SECRET_KEY en .env")
        if not self.publishable_key:
            raise ValueError(f"No se encontró STRIPE_{self.environment.upper()}_PUBLISHABLE_KEY en .env")
        
        # Configurar stripe
        stripe.api_key = self.api_key
    
    def verify_connection(self) -> dict:
        """
        Verifica la conexión a Stripe obteniendo información de la cuenta.
        
        Returns:
            dict: Información de la cuenta de Stripe
        """
        try:
            account = stripe.Account.retrieve()
            return {
                'status': 'conectado',
                'ambiente': self.environment,
                'email': account.get('email'),
                'business_name': account.get('business_profile', {}).get('name'),
                'country': account.get('country'),
                'id': account.get('id'),
            }
        except stripe.error.AuthenticationError:
            return {
                'status': 'error',
                'mensaje': 'Error de autenticación. Verifica tus claves API.'
            }
        except Exception as e:
            return {
                'status': 'error',
                'mensaje': f'Error al conectar: {str(e)}'
            }
    
    def switch_environment(self, environment: str) -> None:
        """
        Cambia el ambiente activo.
        
        Args:
            environment: 'sandbox' o 'prod'
        """
        self.__init__(environment)


def main():
    """Función principal para pruebas."""
    print("🔗 Conectando a Stripe...\n")
    
    try:
        # Conectar a sandbox
        client = StripeClient('sandbox')
        result = client.verify_connection()
        
        print(f"Ambiente: {result.get('ambiente')}")
        print(f"Estado: {result.get('status')}")
        
        if result['status'] == 'conectado':
            print(f"Email: {result.get('email')}")
            print(f"Negocio: {result.get('business_name')}")
            print(f"País: {result.get('country')}")
            print(f"ID Cuenta: {result.get('id')}")
            print("\n✅ Conexión exitosa!")
        else:
            print(f"❌ {result.get('mensaje')}")
    
    except ValueError as e:
        print(f"❌ Error de configuración: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")


if __name__ == '__main__':
    main()
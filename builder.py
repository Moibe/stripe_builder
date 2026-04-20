import os
import stripe
from dotenv import load_dotenv
from utils import obtener_stripe_key

# Cargar variables de entorno
load_dotenv()


class StripeClient:
    """Cliente para conectarse a Stripe con soporte para múltiples ambientes y negocios."""
    
    def __init__(self, environment: str = None, business: str = None):
        """
        Inicializa el cliente de Stripe.
        
        Args:
            environment: 'sandbox' o 'prod'. Si no se especifica, usa STRIPE_ENV del .env
            business: nombre del negocio (ej. 'splashmix', 'geospace'). Si no se especifica, usa STRIPE_DEFAULT_BUSINESS
        """
        self.environment = environment or os.getenv('STRIPE_ENV', 'sandbox')
        self.business = business or os.getenv('STRIPE_DEFAULT_BUSINESS', 'splashmix')
        
        if self.environment not in ['sandbox', 'prod']:
            raise ValueError(f"Ambiente inválido: {self.environment}. Debe ser 'sandbox' o 'prod'")
        
        # Cargar claves según negocio y ambiente
        biz = self.business.upper()
        env = self.environment.upper()
        self.api_key = os.getenv(f'STRIPE_{biz}_{env}_SECRET_KEY')
        self.publishable_key = os.getenv(f'STRIPE_{biz}_{env}_PUBLISHABLE_KEY')
        
        if not self.api_key:
            raise ValueError(f"No se encontró STRIPE_{biz}_{env}_SECRET_KEY en .env")
        
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
    
    def switch_environment(self, environment: str, business: str = None) -> None:
        """
        Cambia el ambiente activo.
        
        Args:
            environment: 'sandbox' o 'prod'
            business: nombre del negocio (opcional, mantiene el actual)
        """
        self.__init__(environment, business or self.business)


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
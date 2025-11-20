#!/usr/bin/env python3
"""
Script de Verificação da Configuração de IA
Verifica se tudo está configurado corretamente para usar a integração de IA
"""

import os
import sys

def check_python_version():
    """Verifica versão do Python"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print("✅ Python versão:", f"{version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print("❌ Python 3.8+ é necessário")
        return False

def check_dependencies():
    """Verifica se as dependências estão instaladas"""
    dependencies = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google.generativeai": "Google Generative AI"
    }
    
    all_ok = True
    for module, name in dependencies.items():
        try:
            __import__(module)
            print(f"✅ {name} instalado")
        except ImportError:
            print(f"❌ {name} NÃO instalado - Execute: pip install {module}")
            all_ok = False
    
    return all_ok

def check_encryption_key():
    """Verifica se ENCRYPTION_KEY está configurada"""
    # Try to load from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not available, continue with os.getenv
    
    key = os.getenv("ENCRYPTION_KEY")
    if key:
        print("✅ ENCRYPTION_KEY configurada")
        return True
    else:
        print("❌ ENCRYPTION_KEY NÃO configurada")
        print("   Execute: python generate_encryption_key.py")
        print("   Adicione ao .env: ENCRYPTION_KEY=sua_chave")
        return False

def check_database_models():
    """Verifica se os modelos do banco estão importáveis"""
    try:
        from app.models.ai_config import AIConfig
        from app.models.license import License
        print("✅ Modelos do banco de dados importados corretamente")
        return True
    except ImportError as e:
        print(f"❌ Erro ao importar modelos: {e}")
        return False

def check_services():
    """Verifica se os serviços estão importáveis"""
    try:
        from app.services.ai_service import AIService, create_ai_service
        from app.services.encryption_service import encrypt, decrypt
        print("✅ Serviços importados corretamente")
        return True
    except ImportError as e:
        print(f"❌ Erro ao importar serviços: {e}")
        return False

def check_endpoints():
    """Verifica se os endpoints estão importáveis"""
    try:
        from app.api.endpoints import ai_config, ai_usage
        print("✅ Endpoints importados corretamente")
        return True
    except ImportError as e:
        print(f"❌ Erro ao importar endpoints: {e}")
        return False

def main():
    """Executa todas as verificações"""
    print("=" * 60)
    print("🔍 VERIFICAÇÃO DA CONFIGURAÇÃO DE IA")
    print("=" * 60)
    print()
    
    checks = [
        ("Versão do Python", check_python_version),
        ("Dependências", check_dependencies),
        ("Chave de Criptografia", check_encryption_key),
        ("Modelos do Banco", check_database_models),
        ("Serviços", check_services),
        ("Endpoints", check_endpoints),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n📋 Verificando {name}...")
        result = check_func()
        results.append((name, result))
    
    print("\n" + "=" * 60)
    print("📊 RESUMO")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{status} - {name}")
        if not result:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 TUDO PRONTO! A integração de IA está configurada corretamente.")
        print("\n📝 Próximos passos:")
        print("   1. Configure uma licença com módulo 'ai' ativo")
        print("   2. Configure o provedor de IA em /super-admin/integracoes/ia")
        print("   3. Teste a conexão")
        print("   4. Comece a usar os endpoints!")
    else:
        print("⚠️  Algumas verificações falharam. Corrija os problemas acima.")
        print("\n📚 Consulte QUICK_START_AI.md para mais detalhes.")
    
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())


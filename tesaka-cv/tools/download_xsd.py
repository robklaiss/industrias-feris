#!/usr/bin/env python3
"""
Script para descargar esquemas XSD oficiales de SIFEN

Uso:
    python -m tools.download_xsd

Descarga los XSD desde:
- https://ekuatia.set.gov.py/sifen/xsd/
"""
import os
import sys
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Optional, Tuple
import re

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

XSD_BASE_URL = "https://ekuatia.set.gov.py/sifen/xsd/"
# Resolver ruta relativa al repo (no hardcodeada)
LOCAL_XSD_DIR = Path(__file__).resolve().parent.parent / "schemas_sifen"

# Archivos opcionales que pueden faltar (404 es aceptable)
OPTIONAL_XSD_PATTERNS = [
    r'.*rde/150/.*Group\.xsd$',
    r'.*RDE_Group\.xsd$',
    r'.*RDE_Ekuatiai_Group\.xsd$',
]


def get_xsd_files_from_index(base_url: str) -> list:
    """
    Obtiene la lista de archivos XSD desde el índice
    
    Returns:
        Lista de URLs de archivos XSD
    """
    try:
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
        
        # Buscar enlaces a archivos .xsd
        xsd_links = re.findall(r'href=["\']([^"\']+\.xsd)["\']', response.text, re.IGNORECASE)
        xsd_files = [urljoin(base_url, link) for link in xsd_links if link.endswith('.xsd')]
        
        # También buscar en listas HTML comunes
        if not xsd_files:
            # Intentar parsear como lista de directorio
            links = re.findall(r'href=["\']([^"\']+)["\']', response.text)
            xsd_files = [
                urljoin(base_url, link) 
                for link in links 
                if link.endswith('.xsd') or 'xsd' in link.lower()
            ]
        
        return list(set(xsd_files))  # Remover duplicados
        
    except Exception as e:
        print(f"⚠️  Error al obtener índice: {e}")
        print(f"   Intentando descargar XSD conocidos directamente...")
        
        # Lista de XSD conocidos basados en estructura típica de SIFEN
        known_xsd = [
            "DE_v150.xsd",
            "DE_v130.xsd", 
            "DE.xsd",
            "DE_v1.5.0.xsd",
            "DE_v1.3.0.xsd",
            "CommonTypes.xsd",
            "types.xsd",
        ]
        
        return [urljoin(base_url, xsd) for xsd in known_xsd]


def is_optional_xsd(url: str) -> bool:
    """
    Verifica si un XSD es opcional (puede estar ausente)
    
    Args:
        url: URL del archivo XSD
        
    Returns:
        True si es opcional
    """
    for pattern in OPTIONAL_XSD_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    return False


def download_xsd(url: str, local_dir: Path, is_optional: bool = False) -> Tuple[bool, bool]:
    """
    Descarga un archivo XSD
    
    Args:
        url: URL del archivo XSD
        local_dir: Directorio local donde guardar
        is_optional: Si True, 404 es un warning, no un error
        
    Returns:
        Tupla (success, was_optional_404)
        success: True si se descargó correctamente
        was_optional_404: True si fue un 404 de un archivo opcional
    """
    try:
        filename = urlparse(url).path.split('/')[-1]
        local_path = local_dir / filename
        
        print(f"📥 Descargando {filename}...", end=" ")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Verificar que es realmente un XSD
        content_type = response.headers.get('Content-Type', '').lower()
        if 'xml' not in content_type and 'text' not in content_type:
            # Verificar contenido
            if not response.text.strip().startswith('<?xml') and 'schema' not in response.text.lower():
                print(f"❌ (no parece ser XML/XSD)")
                return False, False
        
        local_path.write_bytes(response.content)
        size_kb = len(response.content) / 1024
        print(f"✅ ({size_kb:.1f} KB)")
        return True, False
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            if is_optional:
                print(f"⚠️  (opcional, no encontrado)")
                return False, True  # No es error fatal
            else:
                print(f"❌ (no encontrado)")
                return False, False
        else:
            print(f"❌ (error HTTP {e.response.status_code})")
            return False, False
    except Exception as e:
        print(f"❌ ({str(e)[:50]})")
        return False, False


def normalize_schema_location(location: str, base_url: str) -> Optional[str]:
    """
    Normaliza y valida un schemaLocation
    
    Args:
        location: Valor de schemaLocation (puede ser parte de un par en xsi:schemaLocation)
        base_url: URL base para resolver rutas relativas
        
    Returns:
        URL normalizada o None si es inválida
    """
    # Remover espacios y caracteres de control
    location = location.strip()
    
    # Rechazar si contiene espacios (excepto si es xsi:schemaLocation con pares)
    if ' ' in location and not location.startswith('http'):
        return None
    
    # Rechazar si no parece ser una URL o path válido
    if not location or location.startswith(' ') or location.endswith(' '):
        return None
    
    # Si es relativo, resolver contra base_url
    if not location.startswith('http://') and not location.startswith('https://'):
        url = urljoin(base_url, location)
    else:
        url = location
    
    # Solo aceptar URLs que terminen en .xsd
    if not url.endswith('.xsd'):
        return None
    
    return url


def resolve_xsd_imports(xsd_content: str, base_url: str, downloaded: set) -> list:
    """
    Resuelve imports e includes en un XSD para encontrar dependencias
    
    Maneja correctamente:
    - xs:include/@schemaLocation
    - xs:import/@schemaLocation
    - xsi:schemaLocation (pares namespace, location) - solo toma locations (índices impares)
    
    Args:
        xsd_content: Contenido del XSD
        base_url: URL base para resolver rutas relativas
        downloaded: Set de URLs ya descargadas
        
    Returns:
        Lista de URLs de XSD a descargar (normalizadas y validadas)
    """
    imports = []
    
    # Buscar xs:include y xs:import con schemaLocation
    # Patrón: <xs:include schemaLocation="..."/>
    include_pattern = r'<xs:include[^>]+schemaLocation\s*=\s*["\']([^"\']+)["\']'
    import_pattern = r'<xs:import[^>]+schemaLocation\s*=\s*["\']([^"\']+)["\']'
    
    for pattern in [include_pattern, import_pattern]:
        matches = re.findall(pattern, xsd_content, re.IGNORECASE)
        for match in matches:
            url = normalize_schema_location(match, base_url)
            if url and url not in downloaded:
                imports.append(url)
    
    # Buscar xsi:schemaLocation (puede estar en XML de instancia)
    # Formato: xsi:schemaLocation="namespace1 location1 namespace2 location2 ..."
    # Solo necesitamos las locations (índices impares después de split)
    xsi_pattern = r'xsi:schemaLocation\s*=\s*["\']([^"\']+)["\']'
    xsi_matches = re.findall(xsi_pattern, xsd_content, re.IGNORECASE)
    
    for match in xsi_matches:
        # Dividir por whitespace
        tokens = match.split()
        # Tomar solo índices impares (1, 3, 5, ...) que son las locations
        for i in range(1, len(tokens), 2):
            location = tokens[i]
            url = normalize_schema_location(location, base_url)
            if url and url not in downloaded:
                imports.append(url)
    
    return list(set(imports))


def main():
    """Función principal"""
    print("🔍 Buscando esquemas XSD oficiales de SIFEN...")
    print(f"📁 Directorio destino: {LOCAL_XSD_DIR}")
    print()
    
    # Crear directorio si no existe
    LOCAL_XSD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Obtener lista de XSD
    xsd_urls = get_xsd_files_from_index(XSD_BASE_URL)
    
    if not xsd_urls:
        print("⚠️  No se encontraron archivos XSD en el índice.")
        print("   Verifica manualmente: https://ekuatia.set.gov.py/sifen/xsd/")
        return 1
    
    print(f"📋 Encontrados {len(xsd_urls)} archivo(s) XSD:")
    for url in xsd_urls:
        print(f"   - {urlparse(url).path.split('/')[-1]}")
    print()
    
    # Descargar archivos
    downloaded = set()
    failed = []
    optional_missing = []
    
    for url in xsd_urls:
        is_optional = is_optional_xsd(url)
        success, was_optional_404 = download_xsd(url, LOCAL_XSD_DIR, is_optional=is_optional)
        
        if success:
            downloaded.add(url)
            
            # Resolver imports/includes
            try:
                local_file = LOCAL_XSD_DIR / urlparse(url).path.split('/')[-1]
                if local_file.exists():
                    content = local_file.read_text(encoding='utf-8')
                    imports = resolve_xsd_imports(content, url, downloaded)
                    
                    for imp_url in imports:
                        if imp_url not in downloaded and imp_url not in failed and imp_url not in optional_missing:
                            imp_is_optional = is_optional_xsd(imp_url)
                            filename = urlparse(imp_url).path.split('/')[-1]
                            print(f"   └─ Resolviendo dependencia: {filename}...")
                            imp_success, imp_was_optional_404 = download_xsd(imp_url, LOCAL_XSD_DIR, is_optional=imp_is_optional)
                            
                            if imp_success:
                                downloaded.add(imp_url)
                            elif imp_was_optional_404:
                                optional_missing.append(imp_url)
                            else:
                                failed.append(imp_url)
            except Exception as e:
                print(f"   ⚠️  Error resolviendo imports: {e}")
        elif was_optional_404:
            optional_missing.append(url)
        else:
            failed.append(url)
    
    print()
    print(f"✅ Descargados: {len(downloaded)} archivo(s)")
    if optional_missing:
        print(f"⚠️  Opcionales faltantes: {len(optional_missing)} archivo(s)")
        for url in optional_missing:
            filename = urlparse(url).path.split('/')[-1]
            print(f"   - {filename}")
    if failed:
        print(f"❌ Fallidos reales: {len(failed)} archivo(s)")
        for url in failed:
            filename = urlparse(url).path.split('/')[-1]
            print(f"   - {filename}")
    
    # Resumen final
    print()
    print("=" * 60)
    print(f"Resumen: Descargados: {len(downloaded)} / Opcionales faltantes: {len(optional_missing)} / Fallidos reales: {len(failed)}")
    print("=" * 60)
    
    # Buscar el XSD principal (DE_v150.xsd o similar)
    xsd_files = list(LOCAL_XSD_DIR.glob("*.xsd"))
    de_xsd = [f for f in xsd_files if 'DE' in f.name and ('v150' in f.name.lower() or 'v1.5.0' in f.name.lower() or 'v1.3.0' in f.name.lower() or 'v130' in f.name.lower())]
    
    if de_xsd:
        print(f"\n📌 XSD principal encontrado: {de_xsd[0].name}")
    else:
        print(f"\n⚠️  No se encontró XSD principal (DE_v150.xsd). Verifica manualmente.")
        if xsd_files:
            print("   Archivos XSD disponibles:")
            for f in xsd_files:
                print(f"   - {f.name}")
    
    # Exit code 0 si descargamos al menos algunos archivos
    # (incluso si hay opcionales faltantes, eso está bien)
    return 0 if len(downloaded) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())


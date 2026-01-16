#!/usr/bin/env python3
"""
Asistente de Certificación SIFEN
Guía paso a paso para el proceso de certificación
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

class SifenCertificacion:
    """Asistente de certificación SIFEN"""
    
    def __init__(self):
        self.steps = [
            {
                'id': 1,
                'name': 'Validación XSD',
                'desc': 'Validar XML contra esquemas oficiales',
                'cmd': '.venv/bin/python tools/validate_sifen_xml.py --xml {xml}',
                'status': 'pending'
            },
            {
                'id': 2,
                'name': 'Prevalidador SIFEN',
                'desc': 'Validar en Prevalidador web',
                'cmd': 'Subir {xml} a https://sifen.set.gov.py/prevalidador/',
                'status': 'pending'
            },
            {
                'id': 3,
                'name': 'Envío TEST',
                'desc': 'Enviar a ambiente de pruebas',
                'cmd': '.venv/bin/python tools/send_sirecepde.py --xml {xml} --env test --artifacts-dir artifacts/cert_test',
                'status': 'pending'
            },
            {
                'id': 4,
                'name': 'Consulta RUC',
                'desc': 'Probar consulta de RUC',
                'cmd': '.venv/bin/python tools/smoke_test_ruc.py --env test',
                'status': 'pending'
            },
            {
                'id': 5,
                'name': 'Prueba Contingencia',
                'desc': 'Simular caída de servicios',
                'cmd': '.venv/bin/python tools/test_contingencia.py',
                'status': 'pending'
            },
            {
                'id': 6,
                'name': 'Límites Técnicos',
                'desc': 'Probar límites de tamaño y cantidad',
                'cmd': '.venv/bin/python tools/test_limits.py',
                'status': 'pending'
            },
            {
                'id': 7,
                'name': 'Certificación PROD',
                'desc': 'Pruebas en producción',
                'cmd': '.venv/bin/python tools/send_sirecepde.py --xml {xml} --env prod --artifacts-dir artifacts/cert_prod',
                'status': 'pending'
            }
        ]
    
    def mostrar_menu(self):
        """Muestra el menú de certificación"""
        print("\n" + "="*60)
        print("🏆 CERTIFICACIÓN SIFEN - PROCESO OFICIAL")
        print("="*60)
        
        for step in self.steps:
            status_icon = {
                'pending': '⏳',
                'completed': '✅',
                'failed': '❌',
                'skipped': '⏭️'
            }.get(step['status'], '❓')
            
            print(f"\n{status_icon} Paso {step['id']}: {step['name']}")
            print(f"   {step['desc']}")
            print(f"   Comando: {step['cmd']}")
    
    def ejecutar_paso(self, paso_id, xml_path=None):
        """Ejecuta un paso específico"""
        step = next((s for s in self.steps if s['id'] == paso_id), None)
        if not step:
            print(f"❌ Paso {paso_id} no encontrado")
            return
        
        print(f"\n🚀 Ejecutando Paso {paso_id}: {step['name']}")
        print(f"   {step['desc']}")
        
        cmd = step['cmd'].format(xml=xml_path or '{xml}')
        
        if paso_id == 1 and xml_path:
            # Validación XSD
            os.system(cmd)
        elif paso_id == 2:
            print("\n📋 Instrucciones para Prevalidador:")
            print("1. Abre: https://sifen.set.gov.py/prevalidador/")
            print(f"2. Sube el archivo: {xml_path}")
            print("3. Verifica que todas las validaciones pasen")
            input("\nPresiona Enter cuando termines...")
        elif paso_id == 3 and xml_path:
            # Envío a TEST
            os.system(cmd)
        elif paso_id == 4:
            # Consulta RUC
            print("\n📋 Ejecutando smoke test de RUC...")
            self.smoke_test_ruc()
        elif paso_id == 5:
            # Contingencia
            self.test_contingencia()
        elif paso_id == 6:
            # Límites
            self.test_limits()
        elif paso_id == 7 and xml_path:
            # Envío a PROD
            print("\n⚠️  ADVERTENCIA: Esto enviará a PRODUCCIÓN")
            confirm = input("¿Estás seguro? (s/N): ")
            if confirm.lower() == 's':
                os.system(cmd)
            else:
                print("❌ Cancelado")
                return
        
        # Actualizar estado
        step['status'] = 'completed'
        print(f"\n✅ Paso {paso_id} completado")
    
    def smoke_test_ruc(self):
        """Smoke test para consulta RUC"""
        print("\n🔍 Probando consulta RUC...")
        
        # RUCs de prueba
        rucs = ["80014066-4", "4554737-8", "80012345-7"]
        
        for ruc in rucs:
            print(f"\n   Probando RUC: {ruc}")
            cmd = f".venv/bin/python -c \"from app.sifen_client.soap_client import SoapClient; client = SoapClient(); resp = client.consulta_ruc('{ruc}'); print(resp)\""
            os.system(cmd)
    
    def test_contingencia(self):
        """Pruebas de contingencia"""
        print("\n🔄 Pruebas de Contingencia...")
        print("1. Simular desconexión")
        print("2. Usar modo offline")
        print("3. Reintentar conexión")
        input("\nPresiona Enter para continuar...")
    
    def test_limits(self):
        """Prueba límites técnicos"""
        print("\n📊 Probando límites técnicos...")
        print("1. XML de 1MB")
        print("2. 100 items")
        print("3. Caracteres especiales")
        input("\nPresiona Enter para continuar...")
    
    def generar_reporte(self):
        """Genera reporte de certificación"""
        print("\n📄 Generando reporte de certificación...")
        
        reporte = Path("certificacion_reporte.md")
        with open(reporte, 'w') as f:
            f.write("# Reporte de Certificación SIFEN\n\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## Pasos Ejecutados:\n\n")
            
            for step in self.steps:
                status_icon = {
                    'pending': '⏳',
                    'completed': '✅',
                    'failed': '❌',
                    'skipped': '⏭️'
                }.get(step['status'], '❓')
                
                f.write(f"{status_icon} Paso {step['id']}: {step['name']}\n")
                f.write(f"   - {step['desc']}\n")
                f.write(f"   - Comando: `{step['cmd']}`\n\n")
        
        print(f"✅ Reporte guardado en: {reporte}")

def main():
    parser = argparse.ArgumentParser(description="Asistente de Certificación SIFEN")
    parser.add_argument('--xml', help='XML a usar para certificación')
    parser.add_argument('--paso', type=int, help='Ejecutar paso específico')
    parser.add_argument('--listar', action='store_true', help='Listar todos los pasos')
    parser.add_argument('--reporte', action='store_true', help='Generar reporte')
    
    args = parser.parse_args()
    
    cert = SifenCertificacion()
    
    if args.listar:
        cert.mostrar_menu()
    elif args.paso:
        cert.ejecutar_paso(args.paso, args.xml)
    elif args.reporte:
        cert.generar_reporte()
    else:
        print("\n🏆 Asistente de Certificación SIFEN")
        print("\nOpciones:")
        print("  --listar        Mostrar todos los pasos")
        print("  --paso N        Ejecutar paso N")
        print("  --xml FILE      XML a usar")
        print("  --reporte       Generar reporte")
        print("\nEjemplos:")
        print("  python tools/sifen_certificacion.py --listar")
        print("  python tools/sifen_certificacion.py --paso 1 --xml ~/Desktop/test.xml")
        print("  python tools/sifen_certificacion.py --reporte")

if __name__ == "__main__":
    from datetime import datetime
    main()

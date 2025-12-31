package com.roshka.sifen.smoketest;

import com.roshka.sifen.Sifen;
import com.roshka.sifen.core.SifenConfig;
import com.roshka.sifen.core.beans.response.RespuestaConsultaRUC;
import com.roshka.sifen.core.exceptions.SifenException;
import com.roshka.sifen.core.fields.response.ruc.TxContRuc;

import java.io.File;

/**
 * Smoke test para validar conectividad con SIFEN (ambiente DEV).
 * 
 * Ejecuta una consulta RUC contra SIFEN y muestra el resultado.
 */
public class Smoketest {
    
    private static final String DEFAULT_ENV = "DEV";
    
    public static void main(String[] args) {
        try {
            // Leer variables de entorno
            String sifenEnv = getEnvVar("SIFEN_ENV", DEFAULT_ENV);
            String pfxPath = getEnvVar("PFX_PATH", null);
            String pfxPassword = getEnvVar("PFX_PASSWORD", null);
            String cscId = getEnvVar("CSC_ID", null);
            String csc = getEnvVar("CSC", null);
            String rucQuery = getEnvVar("RUC_QUERY", null);
            
            // Validar variables requeridas
            if (pfxPath == null || pfxPath.trim().isEmpty()) {
                System.err.println("ERROR: PFX_PATH no está definido");
                System.exit(1);
            }
            
            if (pfxPassword == null || pfxPassword.trim().isEmpty()) {
                System.err.println("ERROR: PFX_PASSWORD no está definido");
                System.exit(1);
            }
            
            if (rucQuery == null || rucQuery.trim().isEmpty()) {
                System.err.println("ERROR: RUC_QUERY no está definido");
                System.exit(1);
            }
            
            // Validar que el archivo PFX existe
            File pfxFile = new File(pfxPath);
            if (!pfxFile.exists() || !pfxFile.isFile()) {
                System.err.println("ERROR: El archivo PFX no existe: " + pfxPath);
                System.exit(1);
            }
            
            // Extraer RUC sin DV (si viene con formato RUC-DV)
            String ruc = extractRuc(rucQuery);
            
            // Configurar ambiente
            SifenConfig.TipoAmbiente ambiente;
            try {
                ambiente = SifenConfig.TipoAmbiente.valueOf(sifenEnv.toUpperCase());
            } catch (IllegalArgumentException e) {
                System.err.println("ERROR: SIFEN_ENV debe ser DEV o PROD, se recibió: " + sifenEnv);
                System.exit(1);
                return; // Para evitar warning de compilador
            }
            
            // Crear configuración de SIFEN
            SifenConfig config;
            if (cscId != null && !cscId.trim().isEmpty() && csc != null && !csc.trim().isEmpty()) {
                config = new SifenConfig(
                    ambiente,
                    cscId.trim(),
                    csc.trim(),
                    SifenConfig.TipoCertificadoCliente.PFX,
                    pfxPath,
                    pfxPassword
                );
            } else {
                config = new SifenConfig(
                    ambiente,
                    SifenConfig.TipoCertificadoCliente.PFX,
                    pfxPath,
                    pfxPassword
                );
            }
            
            // Establecer configuración global
            Sifen.setSifenConfig(config);
            
            // Ejecutar consulta RUC
            System.out.println("Consultando RUC: " + ruc + " (ambiente: " + ambiente + ")");
            RespuestaConsultaRUC respuesta = Sifen.consultaRUC(ruc);
            
            // Mostrar resultado
            int codigoEstado = respuesta.getCodigoEstado();
            String codRes = respuesta.getdCodRes();
            String msgRes = respuesta.getdMsgRes();
            
            if (codigoEstado == 200 && codRes != null && codRes.equals("0500")) {
                // Éxito
                System.out.println("SMOKETEST: OK");
                System.out.println("Código HTTP: " + codigoEstado);
                System.out.println("Código Respuesta: " + codRes);
                if (msgRes != null) {
                    System.out.println("Mensaje: " + msgRes);
                }
                
                // Mostrar datos del contribuyente
                TxContRuc contribuyente = respuesta.getxContRUC();
                if (contribuyente != null) {
                    System.out.println("\nDatos del Contribuyente:");
                    if (contribuyente.getdRUCCons() != null) {
                        System.out.println("  RUC: " + contribuyente.getdRUCCons());
                    }
                    if (contribuyente.getdRazCons() != null) {
                        System.out.println("  Razón Social: " + contribuyente.getdRazCons());
                    }
                    if (contribuyente.getdCodEstCons() != null) {
                        System.out.println("  Código Estado: " + contribuyente.getdCodEstCons());
                    }
                    if (contribuyente.getdDesEstCons() != null) {
                        System.out.println("  Descripción Estado: " + contribuyente.getdDesEstCons());
                    }
                    if (contribuyente.getdRUCFactElec() != null) {
                        System.out.println("  RUC Facturación Electrónica: " + contribuyente.getdRUCFactElec());
                    }
                }
            } else {
                // Error en la respuesta
                System.out.println("SMOKETEST: FAIL");
                System.out.println("Código HTTP: " + codigoEstado);
                System.out.println("Código Respuesta: " + (codRes != null ? codRes : "N/A"));
                if (msgRes != null) {
                    System.out.println("Mensaje: " + msgRes);
                }
                System.exit(1);
            }
            
        } catch (SifenException e) {
            System.out.println("SMOKETEST: FAIL");
            System.out.println("Excepción SIFEN: " + e.getMessage());
            if (e.getCause() != null) {
                System.out.println("Causa: " + e.getCause().getMessage());
            }
            e.printStackTrace();
            System.exit(1);
        } catch (Exception e) {
            System.out.println("SMOKETEST: FAIL");
            System.out.println("Error inesperado: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
    
    /**
     * Obtiene una variable de entorno o retorna un valor por defecto.
     */
    private static String getEnvVar(String name, String defaultValue) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            return defaultValue;
        }
        return value;
    }
    
    /**
     * Extrae el RUC sin el dígito verificador.
     * Si viene como "80012345-7", retorna "80012345".
     * Si viene como "80012345", retorna "80012345".
     */
    private static String extractRuc(String rucQuery) {
        if (rucQuery == null) {
            return null;
        }
        
        String ruc = rucQuery.trim();
        
        // Si contiene un guión, tomar solo la parte antes del guión
        int dashIndex = ruc.indexOf('-');
        if (dashIndex > 0) {
            ruc = ruc.substring(0, dashIndex);
        }
        
        return ruc;
    }
}


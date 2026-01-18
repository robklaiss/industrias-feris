def send_sirecepde(
    xml_path: Path,
    env: str = "test",
    artifacts_dir: Optional[Path] = None,
    dump_http: bool = False,
    skip_ruc_gate: Optional[bool] = None,
    skip_ruc_gate_reason: Optional[str] = None,
    bump_doc: Optional[str] = None,
    strict_xsd: bool = False,
    xsd_dir: Optional[str] = None,
    lote_source: Optional[str] = None,
    goto_send: bool = False
) -> dict:
    """
    Envía un XML siRecepDE al servicio SOAP de Recepción de SIFEN
    
    Args:
        xml_path: Path al archivo XML siRecepDE
        env: Ambiente ('test' o 'prod')
        artifacts_dir: Directorio para guardar respuestas (opcional)
        lote_source: 'last_lote' (default) para usar artifacts/last_lote.xml o 'memory'
        
    Returns:
        Diccionario con resultado del envío
    """
    # Inicializar variable did para evitar UnboundLocalError
    did = None
    # Inicializar goto_send
    goto_send = goto_send  # Usar el parámetro
    
    # Configurar bypass del GATE (puede venir por ENV o CLI)
    env_skip_gate = os.getenv("SIFEN_SKIP_RUC_GATE", "").strip().lower() in ("1", "true", "yes", "y", "s", "si")
    gate_bypass_active = env_skip_gate or bool(skip_ruc_gate)
    if gate_bypass_active:
        if skip_ruc_gate:
            gate_bypass_reason = skip_ruc_gate_reason or "CLI --skip-ruc-gate"
        elif env_skip_gate:
            gate_bypass_reason = skip_ruc_gate_reason or "ENV:SIFEN_SKIP_RUC_GATE=1"
        else:
            gate_bypass_reason = skip_ruc_gate_reason
    else:
        gate_bypass_reason = None

    # Leer XML como bytes
    print(f"📄 Cargando XML: {xml_path}")
    try:
        xml_bytes = xml_path.read_bytes()
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al leer archivo XML: {str(e)}",
            "error_type": type(e).__name__
        }
    
    # Detectar si el XML ya es un lote rLoteDE (pre-firmado)
    input_is_lote = False
    xml_root_original = None
    
    # DEBUG: Check dVerFor in original bytes
    print(f"🔍 DEBUG: dVerFor en xml_bytes original: {b'<dVerFor>150</dVerFor>' in xml_bytes}")
    
    try:
        parser_detect = etree.XMLParser(remove_blank_text=False)
        xml_root_original = etree.fromstring(xml_bytes, parser=parser_detect)
        input_is_lote = local_tag(xml_root_original.tag) == "rLoteDE"
        
        # DEBUG: Check after parsing
        if input_is_lote:
            rde_nodes = xml_root_original.xpath(".//*[local-name()='rDE']")
            if rde_nodes:
                dVerFor = rde_nodes[0].find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
                print(f"🔍 DEBUG: dVerFor después de parsear: {dVerFor is not None}")
                if dVerFor is not None:
                    print(f"   Valor: {dVerFor.text}")
                    
    except Exception as e:
        # Si falla el parse, continuar (se detectará más adelante)
        print(f"⚠️  WARNING: No se pudo parsear XML para detección de lote: {e}")
        import traceback
        traceback.print_exc()

    # Normalización/bump solo si NO es lote prearmado
    if not input_is_lote:
        xml_bytes = normalize_despaisrec_tags(xml_bytes)
        xml_bytes = apply_timbrado_override(xml_bytes, artifacts_dir=artifacts_dir)

        if bump_doc:
            try:
                xml_bytes = apply_bump_doc(
                    xml_bytes=xml_bytes,
                    bump_doc_value=bump_doc,
                    env=env,
                    artifacts_dir=artifacts_dir,
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"No se pudo aplicar bump-doc ({bump_doc}): {e}",
                    "error_type": type(e).__name__,
                }
    else:
        if bump_doc:
            print("⚠️  WARNING: Ignorando --bump-doc porque el archivo ya es un rLoteDE firmado.")
    
    xml_size = len(xml_bytes)
    print(f"   Tamaño: {xml_size} bytes ({xml_size / 1024:.2f} KB)\n")
    
    # Import config module needed later
    try:
        from app.sifen_client.config import get_sifen_config
    except ImportError:
        get_sifen_config = None
    
    # Validar RUC del emisor antes de enviar (evitar código 1264)
    # Solo validar si no está activo el bypass del gate
    if not gate_bypass_active:
        try:
            from app.sifen_client.ruc_validator import validate_emisor_ruc
            
            # Obtener RUC esperado del config si está disponible
            try:
                config = get_sifen_config(env=env)
                expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or getattr(config, 'test_ruc', None)
            except:
                expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC")
            
            xml_content_str = xml_bytes.decode('utf-8') if isinstance(xml_bytes, bytes) else xml_bytes
            is_valid, error_msg = validate_emisor_ruc(xml_content_str, expected_ruc=expected_ruc)
            
            if not is_valid:
                print(f"❌ RUC emisor inválido/dummy/no coincide; no se envía a SIFEN:")
                print(f"   {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": "RUCValidationError",
                    "note": "Configure SIFEN_EMISOR_RUC con el RUC real del contribuyente habilitado (formato: RUC-DV, ej. 4554737-8)"
                }
            
            print("✓ RUC del emisor validado (no es dummy)\n")
        except ImportError:
            # Si no se puede importar el validador, continuar sin validación (no crítico)
            print("⚠️  No se pudo importar validador de RUC, continuando sin validación\n")
        except Exception as e:
            # Si falla la validación por otro motivo, continuar (no bloquear)
            print(f"⚠️  Error en validación de RUC (no bloqueante): {e}\n")
    else:
        print(f"⚠️  Bypass de validación RUC activo: {gate_bypass_reason}\n")
    
    # Validar variables de entorno requeridas
    required_vars = ['SIFEN_CERT_PATH', 'SIFEN_CERT_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        return {
            "success": False,
            "error": f"Variables de entorno faltantes: {', '.join(missing_vars)}",
            "error_type": "ConfigurationError",
            "note": "Configure estas variables en .env o en el entorno"
        }
    ruc_emisor_for_diag: Optional[str] = None
    ruc_gate_cached: Optional[str] = None
    ruc_check_data: Optional[Dict[str, Any]] = None
    
    # Configurar cliente SIFEN
    print(f"🔧 Configurando cliente SIFEN (ambiente: {env})...")
    if get_sifen_config is None:
        error_msg = "No se pudo importar get_sifen_config (módulo app.sifen_client.config no disponible)"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "error_type": "ImportError"
        }
    
    try:
        config = get_sifen_config(env=env)
        service_key = "recibe_lote"  # Usar servicio de lote (async)
        wsdl_url = config.get_soap_service_url(service_key)
        print(f"   WSDL (recibe_lote): {wsdl_url}")
        print(f"   Operación: siRecepLoteDE\n")
    except Exception as e:
        error_msg = f"Error al configurar cliente SIFEN: {str(e)}"
        print(f"❌ {error_msg}")
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if debug_enabled:
            import traceback
            traceback.print_exc()
        return {
            "success": False,
            "error": error_msg,
            "error_type": type(e).__name__
        }
    
    # Construir XML de lote (rEnvioLote) desde el XML original
    goto_send = False  # Flag para indicar si debemos saltar directamente al envío (modo AS-IS)
    try:
        if input_is_lote:
            print("📦 Usando lote provisto (rLoteDE) — se omite firma P12")
            try:
                lote_root = xml_root_original if xml_root_original is not None else etree.fromstring(xml_bytes)
            except Exception as e:
                raise RuntimeError(f"No se pudo parsear el lote provisto: {e}") from e

            rde_nodes = lote_root.xpath(".//*[local-name()='rDE']")
            if not rde_nodes:
                raise RuntimeError("El XML provisto es rLoteDE pero no contiene ningún rDE")
            has_sifen_ns = any(etree.QName(el).namespace == SIFEN_NS for el in rde_nodes if isinstance(el.tag, str))
            if not has_sifen_ns:
                raise RuntimeError("El rLoteDE provisto no contiene rDE en el namespace SIFEN")

            first_de = None
            for elem in rde_nodes[0].xpath(".//*[local-name()='DE']"):
                first_de = elem
                break
            de_id_detected = first_de.get("Id") if first_de is not None else None
            signature_present = bool(lote_root.xpath(".//*[local-name()='Signature']"))
            print(
                f"   rDE count={len(rde_nodes)}, "
                f"DE.Id={de_id_detected or 'N/A'}, "
                f"Signature={'sí' if signature_present else 'no'}"
            )

            structure = _analyze_lote_structure(lote_root)
            if not structure.valid:
                raise RuntimeError(
                    structure.message
                    or "El rLoteDE provisto no cumple la estructura mínima (rDE directo o xDE -> rDE)."
                )

            normalized_lote_root = lote_root
            if structure.direct_rde_sifen_count > 0 and structure.xde_wrapper_count == 0:
                normalized_lote_root = _wrap_direct_rde_with_xde(lote_root)
                # ✅ MUY IMPORTANTE: estos bytes son los que deben ir al ZIP
                xml_bytes = etree.tostring(
                    normalized_lote_root,
                    xml_declaration=True,
                    encoding="utf-8",
                    pretty_print=False,
                )
                # ✅ y este tree es el que debe seguir el flujo (huellas, guards, etc.)
                xml_root_original = normalized_lote_root
                print(
                    f"   ↺ Normalizado: {structure.direct_rde_sifen_count} rDE directos envueltos en xDE "
                    "para cumplir con el layout esperado."
                )

            lote_xml_bytes = xml_bytes
            zip_bytes = _zip_lote_xml_bytes(lote_xml_bytes)
            import base64
            zip_base64 = base64.b64encode(zip_bytes).decode("ascii")
            print("✓ Lote provisto validado\n")
            
            # DEBUG: Check dVerFor before sending
            if b'<dVerFor>150</dVerFor>' in lote_xml_bytes:
                print("✅ DEBUG: dVerFor encontrado en lote_xml_bytes")
            else:
                print("❌ DEBUG: dVerFor NO encontrado en lote_xml_bytes")
                # Show what we have instead
                if b'<rDE' in lote_xml_bytes:
                    start = lote_xml_bytes.find(b'<rDE')
                    end = lote_xml_bytes.find(b'>', start) + 1
                    print(f"   rDE opening: {lote_xml_bytes[start:end]}")
            
            # MODO AS-IS: Para lotes pre-armados, omitir el flujo normal de _select_lote_payload
            # y usar directamente el lote proporcionado por el usuario
            print(f"📦 Modo LOTE AS-IS: usando el XML tal cual se recibió: {xml_path}")
            
            # Opcional: Validación rápida con xmlsec si está disponible
            if os.getenv("SIFEN_VALIDATE_LOTE_BEFORE_SEND", "1") in ("1", "true", "True"):
                try:
                    import subprocess
                    result = subprocess.run(
                        ["xmlsec1", "--verify", "--insecure", "--id-attr:Id", "DE", str(xml_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        print("✅ Validación xmlsec1 del lote: OK")
                    else:
                        print(f"⚠️  Validación xmlsec1 del lote: FALLÓ\n{result.stderr}")
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as ex:
                    print(f"⚠️  No se pudo validar con xmlsec1: {ex}")
            
            # Crear una selección especial para modo AS-IS
            selection = LotePayloadSelection(
                lote_bytes=lote_xml_bytes,
                zip_bytes=zip_bytes,
                zip_base64=zip_base64,
                source=f"file:{xml_path}",
                lote_path=xml_path,
                zip_path=None,
            )
            
            # Para modo AS-IS, saltar directamente al envío (omitir _select_lote_payload)
            print("🔍 DEBUG: Estableciendo goto_send = True")
            goto_send = True
            # Continuar con el flujo normal dentro del try principal
            # No return aquí, dejamos que el flujo continúe al bloque if goto_send más adelante
            print("🔍 DEBUG: Bloque AS-IS completado, continuando...")
            
            # Continuar con el flujo normal...
            print("🔍 DEBUG: Saliendo del bloque if/else de detección de lote")
        else:
            print("🔍 DEBUG: Entrando al bloque else (no es lote pre-firmado)")
            # GUARD-RAIL: Verificar dependencias críticas antes de firmar
            try:
                _check_signing_dependencies()
            except RuntimeError as e:
                error_msg = f"BLOQUEADO: {str(e)}. Ejecutar scripts/bootstrap_env.sh"
                try:
                    if artifacts_dir is None:
                        artifacts_dir = Path("artifacts")
                    artifacts_dir.mkdir(parents=True, exist_ok=True)
                    artifacts_dir.joinpath("sign_blocked_input.xml").write_bytes(xml_bytes)
                    artifacts_dir.joinpath("sign_blocked_reason.txt").write_text(
                        f"BLOQUEADO: Dependencias de firma faltantes\n\n{str(e)}\n\n"
                        f"Ejecutar: scripts/bootstrap_env.sh\n"
                        f"O manualmente: pip install lxml python-xmlsec",
                        encoding="utf-8"
                    )
                except Exception:
                    pass
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": "DependencyError"
                }
        
        print("🔍 DEBUG: Antes de entrar al bloque if goto_send final")
        
        try:
            print("📦 Construyendo y firmando lote desde XML individual...")
            
            # Leer certificado de firma (fallback a mTLS o CERT_PATH si no hay específico de firma)
            sign_cert_path = os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_MTLS_P12_PATH") or os.getenv("SIFEN_CERT_PATH")
            sign_cert_password = os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_MTLS_P12_PASSWORD") or os.getenv("SIFEN_CERT_PASSWORD")
            
            if not sign_cert_path or not sign_cert_password:
                return {
                    "success": False,
                    "error": "Falta certificado de firma (SIFEN_SIGN_P12_PATH o SIFEN_MTLS_P12_PATH y su contraseña)",
                    "error_type": "ConfigurationError"
                }
            
            # Verificar si el XML ya es un lote firmado (rLoteDE)
            xml_root = etree.fromstring(xml_bytes)
            is_already_lote = xml_root.tag == f"{{{SIFEN_NS}}}rLoteDE"
            
            if is_already_lote:
                    print("✓ XML detectado como lote ya firmado (rLoteDE)")
                    # Para lotes ya firmados, solo necesitamos:
                    # 1. Verificar que tenga dVerFor
                    # 2. Crear el ZIP sin modificar el XML
                    # 3. No volver a firmar
                    
                    # Verificar dVerFor
                    rde = xml_root.find(f".//{{{SIFEN_NS}}}rDE")
                    if rde is not None:
                        dver = rde.find(".//dVerFor")
                        if dver is None or dver.text != "150":
                            print("⚠️  Agregando dVerFor=150 al lote existente")
                            dver_elem = etree.SubElement(rde, "dVerFor")
                            dver_elem.text = "150"
                            # Mover dVerFor al principio
                            children = list(rde)
                            rde.clear()
                            rde.append(dver_elem)
                            for child in children:
                                rde.append(child)
                    
                    # Serializar y crear ZIP
                    lote_xml_bytes = etree.tostring(xml_root, xml_declaration=True, encoding="utf-8", pretty_print=False)
                    
                    # Crear ZIP
                    import zipfile
                    import io
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr('lote.xml', lote_xml_bytes)
                    zip_bytes = zip_buffer.getvalue()
                    
                    # Base64
                    import base64
                    zip_base64 = base64.b64encode(zip_bytes).decode('ascii')
                    
                    # Guardar artifacts
                    if artifacts_dir:
                        zip_path = artifacts_dir / "last_lote.zip"
                        zip_path.write_bytes(zip_bytes)
                        lote_path = artifacts_dir / "last_lote.xml"
                        lote_path.write_bytes(lote_xml_bytes)
            else:
                print("🔐 Construyendo lote completo y firmando rDE in-place...")
                # Flujo normal para DE individual
                try:
                    # Crear directorio del run
                    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                    run_dir = (artifacts_dir or Path("artifacts")) / f"runs_async/{timestamp}_{env}"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Guardar DE original (unsigned)
                    de_unsigned_path = run_dir / f"de_unsigned_{timestamp}.xml"
                    de_unsigned_path.write_bytes(xml_bytes)
                    print(f"📄 UNSIGNED: {de_unsigned_path}")
                    
                    # Verificar que DE unsigned no tiene Signature
                    if b'<Signature' in xml_bytes:
                        print("⚠️  WARNING: DE unsigned contiene Signature - no debería tenerla")
                    else:
                        print("✅ DE unsigned verificado: no contiene Signature")
                    
                    # NUEVO FLUJO: construir lote completo ANTES de firmar, luego firmar in-place
                    result = build_and_sign_lote_from_xml(
                        xml_bytes=xml_bytes,
                        cert_path=sign_cert_path,
                        cert_password=sign_cert_password,
                        return_debug=True,
                        dump_http=dump_http
                    )
                    if isinstance(result, tuple):
                        if len(result) == 4:
                            zip_base64, lote_xml_bytes, zip_bytes, _ = result  # _ es None (lote_did ya no existe)
                        else:
                            zip_base64, lote_xml_bytes, zip_bytes = result
                            
                            # Extraer y guardar rDE firmado
                            import xml.etree.ElementTree as ET
                            root = ET.fromstring(lote_xml_bytes)
                            ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
                            rde = root.find('.//sifen:rDE', ns)
                            
                            if rde is not None:
                                rde_bytes = ET.tostring(rde, encoding='utf-8', method='xml')
                                # Extraer ID del DE para el nombre
                                de_elem = rde.find('.//sifen:DE', ns)
                                if de_elem is not None:
                                    de_id = de_elem.get('Id', 'unknown')
                                else:
                                    de_id = 'unknown'
                                
                                # Guardar rDE firmado
                                if artifacts_dir:
                                    rde_signed_path = artifacts_dir / f"rde_signed_{de_id}.xml"
                                    rde_signed_path.write_bytes(rde_bytes)
                                
                                # Extraer y guardar lote.xml del ZIP para debug
                                if zip_bytes:
                                    import zipfile
                                    import io
                                    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                                        with zf.open('lote.xml') as xml_file:
                                            xml_content = xml_file.read()
                                            lote_extraido_path = run_dir / "lote_extraido.xml"
                                            lote_extraido_path.write_bytes(xml_content)
                                
                                print("\n🔍 Comandos para verificación local:")
                                print(f"  xmlsec1 --verify --insecure --id-attr:Id DE {rde_signed_path if 'rde_signed_path' in locals() else lote_extraido_path}")
                                print(f"  xmlsec1 --verify --insecure --id-attr:Id http://ekuatia.set.gov.py/sifen/xsd:DE {lote_extraido_path}")
                                
                                # Continuar con el flujo normal...
                    else:
                        zip_base64 = result
                        zip_bytes = base64.b64decode(zip_base64)
                        lote_xml_bytes = None
                except Exception as e:
                    error_msg = f"Error al construir lote: {str(e)}"
                    error_type = type(e).__name__
                    import traceback
                    traceback.print_exc()
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": error_type,
                        "traceback": traceback.format_exc()
                    }
            # EXTRAER rDE FIRMADO del lote para usarlo en el SOAP
            # El xml_bytes original ya no sirve - necesitamos el rDE firmado
            if zip_bytes:
                import zipfile
                import io
                with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                    with zf.open('lote.xml') as xml_file:
                        lote_content = xml_file.read()
                        # Parsear el lote para extraer el rDE firmado
                        lote_root = etree.fromstring(lote_content)
                        rde_elem = None
                        for elem in lote_root:
                            if elem.tag == '{http://ekuatia.set.gov.py/sifen/xsd}xDE':
                                if len(elem) > 0 and elem[0].tag == '{http://ekuatia.set.gov.py/sifen/xsd}rDE':
                                    rde_elem = elem[0]
                                    break
                        if rde_elem is not None:
                            # Asegurar que dVerFor esté presente
                            dverfor = rde_elem.find(".//dVerFor")
                            if dverfor is None:
                                dverfor = rde_elem.find(f".//{{{SIFEN_NS}}}dVerFor")
                            if dverfor is None:
                                # Agregar dVerFor como primer hijo
                                dverfor_new = etree.SubElement(rde_elem, f"{{{SIFEN_NS}}}dVerFor")
                                dverfor_new.text = "150"
                                rde_elem.insert(0, dverfor_new)
                                print("🔧 dVerFor agregado al rDE extraído del lote")
                            
                            # Actualizar xml_bytes con el rDE firmado
                            xml_bytes = etree.tostring(
                                rde_elem,
                                encoding='utf-8',
                                xml_declaration=True,
                                pretty_print=False
                            )
                            print("✅ xml_bytes actualizado con rDE firmado del lote")
                        else:
                            print("⚠️  No se pudo extraer rDE del lote, usando xml_bytes original")
                
                print("✓ Lote construido y rDE firmado exitosamente\n")
                
                # Guardar artifacts para diagnóstico 0160
                try:
                    artifacts_dir = Path("artifacts")
                    artifacts_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Extraer CDC del XML para nombrar archivos
                    cdc_for_filename = "unknown"
                    try:
                        xml_root = etree.fromstring(xml_bytes)
                        de_elem = xml_root.find(f".//{{{SIFEN_NS}}}DE")
                        if de_elem is None:
                            for elem in xml_root.iter():
                                if isinstance(elem.tag, str) and local_tag(elem.tag) == "DE":
                                    de_elem = elem
                                    break
                        if de_elem is not None:
                            cdc_for_filename = de_elem.get("Id") or de_elem.get("id") or "unknown"
                    except Exception:
                        pass
                    
                    # Extraer dId del XML para nombrar archivos
                    did_for_filename = "unknown"
                    try:
                        xml_root = etree.fromstring(xml_bytes)
                        d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
                        if d_id_elem is not None and d_id_elem.text:
                            did_for_filename = d_id_elem.text.strip()
                    except Exception:
                        pass
                    
                    # Guardar lote_built_<dId>.xml (lote completo final antes de zip)
                    if lote_xml_bytes:
                        lote_built_path = artifacts_dir / f"lote_built_{did_for_filename}.xml"
                        lote_built_path.write_bytes(lote_xml_bytes)
                        print(f"   💾 {lote_built_path}")
                    
                    # Guardar rde_signed_<CDC>.xml (DE firmado con Signature)
                    try:
                        # Extraer rDE firmado del lote
                        if lote_xml_bytes:
                            lote_root = etree.fromstring(lote_xml_bytes)
                            rde_elem = None
                            for elem in lote_root:
                                if isinstance(elem.tag, str) and local_tag(elem.tag) == "rDE":
                                    rde_elem = elem
                                    break
                            if rde_elem is not None:
                                rde_signed_bytes = etree.tostring(
                                    rde_elem,
                                    encoding="utf-8",
                                    xml_declaration=True,
                                    pretty_print=False
                                )
                                rde_signed_path = artifacts_dir / f"rde_signed_{cdc_for_filename}.xml"
                                rde_signed_path.write_bytes(rde_signed_bytes)
                                print(f"   💾 {rde_signed_path}")
                    except Exception as e:
                        print(f"   ⚠️  No se pudo guardar rde_signed: {e}")
                    
                    # Guardar lote_zip_<dId>.zip (ZIP para inspección local)
                    lote_zip_path = artifacts_dir / f"lote_zip_{did_for_filename}.zip"
                    lote_zip_path.write_bytes(zip_bytes)
                    print(f"   💾 {lote_zip_path}")
                    
                except Exception as e:
                    print(f"   ⚠️  Error al guardar artifacts de diagnóstico: {e}")
            
            print("✓ Lote construido y rDE firmado exitosamente\n")
            
            # Construir payload XML para SOAP
            payload_xml = build_r_envio_lote_xml(
                did=did,
                xml_bytes=xml_bytes,
                zip_base64=zip_base64
            )
            
            # Validar payload con XSD (opcional, solo para debug)
            validation_result = validate_xml_with_xsd(payload_xml, env=env)
            
            if not validation_result.valid:
                print(f"❌ Validación XSD fallida: {validation_result.message}")
                if validation_result.xml_path and validation_result.xml_path.exists():
                    print(f"   Ver: {validation_result.xml_path}")
                if validation_result.report_path and validation_result.report_path.exists():
                    print(f"   Reporte: {validation_result.report_path}")
            else:
                print("✅ Validación XSD exitosa")
            
            # Sanity checks: RUC, etc.
            _run_sanity_checks(lote_xml_bytes, cert_path=sign_cert_path)
            
            # Modo AS-IS: usar XML/ZIP tal cual sin firmar ni construir
            print(f"🔍 DEBUG: goto_send = {goto_send}")
            if goto_send:
                try:
                    # Para modo AS-IS, ya tenemos zip_base64 y zip_bytes del lote provisto
                    if not zip_base64:
                        return {
                            "success": False,
                            "error": "No se pudo crear el ZIP del lote",
                            "error_type": "ValidationError"
                        }
                    
                    # Generar dId
                    did = make_did_15()
                    
                    # Construir payload
                    payload_xml = build_r_envio_lote_xml(
                        did=did,
                        xml_bytes=lote_xml_bytes,
                        zip_base64=zip_base64
                    )
                    
                    # Enviar
                    print("\n📡 Enviando a SIFEN (modo AS-IS)...")
                    client = SoapClient(env=env)
                    response = client.recepcion_lote(payload_xml)
                    
                    return {
                        "success": response.ok,
                        "response": response,
                        "payload_xml": payload_xml,
                        "lote_xml_bytes": lote_xml_bytes,
                        "zip_bytes": zip_bytes,
                        "zip_base64": zip_base64,
                        "artifacts_dir": artifacts_dir
                    }
                except Exception as e:
                    error_msg = f"Error en modo AS-IS: {str(e)}"
                    print(f"❌ {error_msg}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": type(e).__name__,
                        "traceback": traceback.format_exc()
                    }
            else:
                try:
                    # Enviar a SIFEN
                    print("\n📡 Enviando a SIFEN...")
                    client = SoapClient(env=env)
                    response = client.recepcion_lote(payload_xml)
                    
                    result = {
                        "success": response.ok,
                        "response": response,
                        "payload_xml": payload_xml,
                        "lote_xml_bytes": lote_xml_bytes,
                        "zip_bytes": zip_bytes,
                        "zip_base64": zip_base64,
                        "validation": validation_result,
                        "artifacts_dir": artifacts_dir
                    }
                except Exception as e:
                    error_msg = f"Error general al procesar: {str(e)}"
                    print(f"❌ {error_msg}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": type(e).__name__,
                        "traceback": traceback.format_exc()
                    }
            # End of if/else block
    
    # Function should never reach here
    return None

export type EstadoSuscripcion = 'activa' | 'prueba' | 'vencida' | 'suspendida';
export type EstadoLiquidacion = 'pendiente' | 'aprobada' | 'pagada' | 'anulada';

export interface PlanSuscripcion {
  id: number;
  codigo: string;
  nombre: string;
  descripcion: string;
  precio_mensual: string;
  comision_porcentaje: string;
  max_tiendas: number;
  max_productos: number | null;
  max_usuarios: number | null;
  activo: boolean;
  creado: string;
}

export interface CrearPlanSuscripcionDto {
  codigo: string;
  nombre: string;
  descripcion: string;
  precio_mensual: number;
  comision_porcentaje: number;
  max_tiendas?: number;
  max_productos?: number | null;
  max_usuarios?: number | null;
  activo?: boolean;
}

export interface MiSuscripcionResponse {
  planes: PlanSuscripcion[];
  tiendas_actuales: number;
  tiendas: Array<{
    tienda_id: number;
    tienda_nombre: string;
    tienda_activa: boolean;
    suscripcion: SuscripcionTienda | null;
  }>;
  suscripcion_actual: SuscripcionTienda | null;
}

export interface IntentoPagoPlanResponse {
  requiere_pago: boolean;
  client_secret?: string;
  payment_intent_id?: string;
  publishable_key?: string;
  monto_bs?: string;
  monto_usd?: string;
  tipo_cambio_usd?: string;
  plan?: PlanSuscripcion;
}

export interface SuscripcionTienda {
  id: number;
  tienda: number;
  tienda_nombre: string;
  plan: number;
  plan_nombre: string;
  max_tiendas: number;
  precio_mensual: string;
  comision_porcentaje: string;
  estado: EstadoSuscripcion;
  fecha_inicio: string;
  fecha_fin: string;
  auto_renovar: boolean;
  actualizado: string;
}

export interface TiendaConSuscripcion {
  tienda_id: number;
  tienda_nombre: string;
  tienda_slug: string;
  tienda_activa: boolean;
  propietario_email: string;
  suscripcion: SuscripcionTienda | null;
}

export interface AsignarSuscripcionDto {
  plan: number;
  estado: EstadoSuscripcion;
  fecha_inicio: string;
  fecha_fin: string;
  auto_renovar: boolean;
}

export interface PrevisualizacionLiquidacion {
  tienda_id: number;
  tienda_nombre: string;
  periodo_inicio: string;
  periodo_fin: string;
  cantidad_pedidos: number;
  total_ventas: string;
  comision_porcentaje: string;
  monto_comision: string;
  monto_neto: string;
}

export interface LiquidacionTienda {
  id: number;
  tienda: number;
  tienda_nombre: string;
  periodo_inicio: string;
  periodo_fin: string;
  cantidad_pedidos: number;
  total_ventas: string;
  comision_porcentaje: string;
  monto_comision: string;
  monto_neto: string;
  estado: EstadoLiquidacion;
  referencia_pago: string;
  notas: string;
  generado_por: number | null;
  generado_por_email: string;
  creado: string;
  pagado_en: string | null;
}

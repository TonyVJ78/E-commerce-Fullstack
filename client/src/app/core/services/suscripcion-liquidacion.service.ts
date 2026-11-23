import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  AsignarSuscripcionDto,
  CrearPlanSuscripcionDto,
  IntentoPagoPlanResponse,
  LiquidacionTienda,
  MiSuscripcionResponse,
  PlanSuscripcion,
  PrevisualizacionLiquidacion,
  SuscripcionTienda,
  TiendaConSuscripcion,
} from '../models/suscripcion.model';

/** Servicio administrativo para Planes de Suscripción y Liquidación de Tiendas (CU-37). */
@Injectable({ providedIn: 'root' })
export class SuscripcionLiquidacionService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiUrl}/finanzas/plataforma`;
  private readonly miSuscripcionUrl = `${environment.apiUrl}/finanzas/mi-suscripcion/`;

  obtenerMiSuscripcion(): Observable<MiSuscripcionResponse> {
    return this.http.get<MiSuscripcionResponse>(this.miSuscripcionUrl);
  }

  iniciarPagoPlan(planId: number): Observable<IntentoPagoPlanResponse> {
    return this.http.post<IntentoPagoPlanResponse>(`${this.miSuscripcionUrl}pago-intento/`, { plan_id: planId });
  }

  seleccionarMiPlan(planId: number, paymentIntentId?: string): Observable<SuscripcionTienda> {
    return this.http.post<SuscripcionTienda>(this.miSuscripcionUrl, {
      plan_id: planId,
      ...(paymentIntentId ? { payment_intent_id: paymentIntentId } : {}),
    });
  }

  listarPlanes(): Observable<PlanSuscripcion[]> {
    return this.http.get<PlanSuscripcion[]>(`${this.baseUrl}/planes/`);
  }

  crearPlan(datos: CrearPlanSuscripcionDto): Observable<PlanSuscripcion> {
    return this.http.post<PlanSuscripcion>(`${this.baseUrl}/planes/`, datos);
  }

  actualizarPlan(id: number, datos: Partial<CrearPlanSuscripcionDto>): Observable<PlanSuscripcion> {
    return this.http.patch<PlanSuscripcion>(`${this.baseUrl}/planes/${id}/`, datos);
  }

  desactivarPlan(id: number): Observable<PlanSuscripcion> {
    return this.http.delete<PlanSuscripcion>(`${this.baseUrl}/planes/${id}/`);
  }

  listarSuscripcionesTiendas(): Observable<{ tiendas: TiendaConSuscripcion[] }> {
    return this.http.get<{ tiendas: TiendaConSuscripcion[] }>(`${this.baseUrl}/suscripciones/`);
  }

  asignarSuscripcion(tiendaId: number, datos: AsignarSuscripcionDto): Observable<SuscripcionTienda> {
    return this.http.post<SuscripcionTienda>(`${this.baseUrl}/tiendas/${tiendaId}/suscripcion/`, datos);
  }

  previsualizarLiquidacion(payload: {
    tienda: number;
    periodo_inicio: string;
    periodo_fin: string;
  }): Observable<PrevisualizacionLiquidacion> {
    return this.http.post<PrevisualizacionLiquidacion>(`${this.baseUrl}/liquidaciones/previsualizar/`, payload);
  }

  listarLiquidaciones(filtros?: { tienda?: number; estado?: string }): Observable<LiquidacionTienda[]> {
    let params = new HttpParams();
    if (filtros?.tienda) params = params.set('tienda', String(filtros.tienda));
    if (filtros?.estado) params = params.set('estado', filtros.estado);
    return this.http.get<LiquidacionTienda[]>(`${this.baseUrl}/liquidaciones/`, { params });
  }

  generarLiquidacion(payload: {
    tienda: number;
    periodo_inicio: string;
    periodo_fin: string;
    notas?: string;
  }): Observable<LiquidacionTienda> {
    return this.http.post<LiquidacionTienda>(`${this.baseUrl}/liquidaciones/`, payload);
  }

  ejecutarAccionLiquidacion(
    id: number,
    accion: 'aprobar' | 'pagar' | 'anular',
    datos?: { referencia_pago?: string; notas?: string }
  ): Observable<LiquidacionTienda> {
    return this.http.post<LiquidacionTienda>(`${this.baseUrl}/liquidaciones/${id}/${accion}/`, datos ?? {});
  }
}

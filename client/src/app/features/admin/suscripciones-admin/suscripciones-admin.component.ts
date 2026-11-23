import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  EstadoSuscripcion,
  LiquidacionTienda,
  PlanSuscripcion,
  PrevisualizacionLiquidacion,
  TiendaConSuscripcion,
} from '../../../core/models/suscripcion.model';
import { SuscripcionLiquidacionService } from '../../../core/services/suscripcion-liquidacion.service';

type Pestana = 'planes' | 'tiendas' | 'liquidaciones';

@Component({
  selector: 'app-suscripciones-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './suscripciones-admin.component.html',
  styleUrls: ['./suscripciones-admin.component.css'],
})
export class SuscripcionesAdminComponent implements OnInit {
  private readonly svc = inject(SuscripcionLiquidacionService);
  private readonly destroyRef = inject(DestroyRef);

  readonly pestana = signal<Pestana>('planes');
  readonly cargando = signal(false);
  readonly mensaje = signal('');
  readonly error = signal('');

  readonly planes = signal<PlanSuscripcion[]>([]);
  readonly tiendas = signal<TiendaConSuscripcion[]>([]);
  readonly liquidaciones = signal<LiquidacionTienda[]>([]);
  readonly previsualizacion = signal<PrevisualizacionLiquidacion | null>(null);

  // Formulario Plan
  planCodigo = '';
  planNombre = '';
  planDescripcion = '';
  planPrecio = 199;
  planComision = 5;
  planMaxProductos: number | null = 100;
  planMaxUsuarios: number | null = 5;

  // Formulario Asignar Suscripción
  tiendaSeleccionadaId: number | null = null;
  planAsignadoId: number | null = null;
  estadoAsignado: EstadoSuscripcion = 'activa';
  fechaInicioSusc = this.hoyIso();
  fechaFinSusc = this.sumarDiasIso(30);

  // Formulario Liquidación
  liqTiendaId: number | null = null;
  liqInicio = this.sumarDiasIso(-30);
  liqFin = this.hoyIso();
  liqNotas = '';
  referenciaPorId: Record<number, string> = {};

  ngOnInit(): void {
    this.cargarTodo();
  }

  cargarTodo(): void {
    this.cargando.set(true);
    this.error.set('');
    this.svc.listarPlanes().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (datos) => {
        this.planes.set(datos);
        if (this.planAsignadoId === null && datos.length > 0) {
          this.planAsignadoId = datos[0].id;
        }
        this.cargando.set(false);
      },
      error: () => {
        this.error.set('No se pudieron cargar los planes de suscripción.');
        this.cargando.set(false);
      },
    });

    this.svc.listarSuscripcionesTiendas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.tiendas.set(res.tiendas);
        if (this.tiendaSeleccionadaId === null && res.tiendas.length > 0) {
          this.tiendaSeleccionadaId = res.tiendas[0].tienda_id;
        }
        if (this.liqTiendaId === null && res.tiendas.length > 0) {
          this.liqTiendaId = res.tiendas[0].tienda_id;
        }
      },
      error: () => {},
    });

    this.svc.listarLiquidaciones().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (datos) => this.liquidaciones.set(datos),
      error: () => {},
    });
  }

  crearPlan(): void {
    this.limpiarAvisos();
    if (!this.planCodigo.trim() || !this.planNombre.trim()) {
      this.error.set('Indica el código y nombre del plan.');
      return;
    }
    this.svc
      .crearPlan({
        codigo: this.planCodigo.trim().toLowerCase(),
        nombre: this.planNombre.trim(),
        descripcion: this.planDescripcion.trim(),
        precio_mensual: Number(this.planPrecio),
        comision_porcentaje: Number(this.planComision),
        max_productos: this.planMaxProductos,
        max_usuarios: this.planMaxUsuarios,
        activo: true,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (nuevo) => {
          this.planes.update((lista) => [...lista, nuevo]);
          this.planCodigo = '';
          this.planNombre = '';
          this.planDescripcion = '';
          this.mensaje.set(`Plan "${nuevo.nombre}" creado correctamente.`);
        },
        error: (err) => this.error.set(err?.error?.error || 'No se pudo crear el plan.'),
      });
  }

  alternarEstadoPlan(plan: PlanSuscripcion): void {
    this.limpiarAvisos();
    if (plan.activo) {
      this.svc.desactivarPlan(plan.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (act) => {
          this.planes.update((l) => l.map((p) => (p.id === act.id ? act : p)));
          this.mensaje.set(`Plan "${act.nombre}" desactivado.`);
        },
        error: (err) => this.error.set(err?.error?.error || 'No se puede desactivar el plan.'),
      });
    } else {
      this.svc.actualizarPlan(plan.id, { activo: true }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (act) => {
          this.planes.update((l) => l.map((p) => (p.id === act.id ? act : p)));
          this.mensaje.set(`Plan "${act.nombre}" reactivado.`);
        },
        error: () => this.error.set('No se pudo reactivar el plan.'),
      });
    }
  }

  asignarSuscripcion(): void {
    this.limpiarAvisos();
    if (!this.tiendaSeleccionadaId || !this.planAsignadoId) {
      this.error.set('Selecciona una tienda y un plan.');
      return;
    }
    this.svc
      .asignarSuscripcion(this.tiendaSeleccionadaId, {
        plan: this.planAsignadoId,
        estado: this.estadoAsignado,
        fecha_inicio: this.fechaInicioSusc,
        fecha_fin: this.fechaFinSusc,
        auto_renovar: true,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.mensaje.set('Suscripción asignada y registrada en bitácora.');
          this.cargarTodo();
        },
        error: (err) => this.error.set(err?.error?.error || 'No se pudo asignar la suscripción.'),
      });
  }

  previsualizar(): void {
    this.limpiarAvisos();
    if (!this.liqTiendaId) {
      this.error.set('Selecciona una tienda para calcular.');
      return;
    }
    this.svc
      .previsualizarLiquidacion({
        tienda: this.liqTiendaId,
        periodo_inicio: this.liqInicio,
        periodo_fin: this.liqFin,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => this.previsualizacion.set(res),
        error: (err) => this.error.set(err?.error?.error || 'No se pudo calcular la liquidación.'),
      });
  }

  generarLiquidacion(): void {
    this.limpiarAvisos();
    if (!this.liqTiendaId) {
      this.error.set('Selecciona una tienda.');
      return;
    }
    this.svc
      .generarLiquidacion({
        tienda: this.liqTiendaId,
        periodo_inicio: this.liqInicio,
        periodo_fin: this.liqFin,
        notas: this.liqNotas,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (liq) => {
          this.liquidaciones.update((l) => [liq, ...l]);
          this.previsualizacion.set(null);
          this.liqNotas = '';
          this.mensaje.set(`Liquidación #${liq.id} generada por Bs ${liq.monto_neto}.`);
        },
        error: (err) => this.error.set(err?.error?.error || 'No se pudo generar la liquidación.'),
      });
  }

  accionLiquidacion(liq: LiquidacionTienda, accion: 'aprobar' | 'pagar' | 'anular'): void {
    this.limpiarAvisos();
    const referencia = (this.referenciaPorId[liq.id] || '').trim();
    if (accion === 'pagar' && !referencia) {
      this.error.set('Ingresa la referencia o comprobante de transferencia antes de pagar.');
      return;
    }
    this.svc
      .ejecutarAccionLiquidacion(liq.id, accion, { referencia_pago: referencia })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (actualizada) => {
          this.liquidaciones.update((l) => l.map((item) => (item.id === actualizada.id ? actualizada : item)));
          this.mensaje.set(`Liquidación #${actualizada.id} actualizada a ${actualizada.estado}.`);
        },
        error: (err) => this.error.set(err?.error?.error || 'No se pudo actualizar la liquidación.'),
      });
  }

  private limpiarAvisos(): void {
    this.mensaje.set('');
    this.error.set('');
  }

  private hoyIso(): string {
    return new Date().toISOString().slice(0, 10);
  }

  private sumarDiasIso(dias: number): string {
    const f = new Date();
    f.setDate(f.getDate() + dias);
    return f.toISOString().slice(0, 10);
  }
}

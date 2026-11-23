import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { loadStripe, Stripe, StripeElements, StripePaymentElement } from '@stripe/stripe-js';
import { environment } from '../../../../environments/environment';
import {
  IntentoPagoPlanResponse,
  MiSuscripcionResponse,
  PlanSuscripcion,
} from '../../../core/models/suscripcion.model';
import { MonedaService, formatearMonto } from '../../../core/services/moneda.service';
import { SuscripcionLiquidacionService } from '../../../core/services/suscripcion-liquidacion.service';

@Component({
  selector: 'app-mi-suscripcion',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './mi-suscripcion.component.html',
  styleUrls: ['./mi-suscripcion.component.css'],
})
export class MiSuscripcionComponent implements OnInit, OnDestroy {
  private readonly servicio = inject(SuscripcionLiquidacionService);
  readonly monedaService = inject(MonedaService);

  readonly cargando = signal(false);
  readonly guardandoPlanId = signal<number | null>(null);
  readonly pagandoStripe = signal(false);
  readonly cargandoStripe = signal(false);
  readonly error = signal<string | null>(null);
  readonly stripeError = signal<string | null>(null);
  readonly mensaje = signal<string | null>(null);
  readonly datos = signal<MiSuscripcionResponse | null>(null);
  readonly planPendiente = signal<PlanSuscripcion | null>(null);
  readonly intentoPago = signal<IntentoPagoPlanResponse | null>(null);

  private stripe: Stripe | null = null;
  private elements: StripeElements | null = null;
  private paymentElement: StripePaymentElement | null = null;

  ngOnInit(): void {
    this.cargar();
  }

  ngOnDestroy(): void {
    this.limpiarStripe();
  }

  cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.servicio.obtenerMiSuscripcion().subscribe({
      next: (res) => {
        this.datos.set(res);
        this.cargando.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.error ?? 'No se pudieron cargar los planes de suscripción.');
        this.cargando.set(false);
      },
    });
  }

  elegirPlan(plan: PlanSuscripcion): void {
    this.guardandoPlanId.set(plan.id);
    this.error.set(null);
    this.stripeError.set(null);
    this.mensaje.set(null);
    this.limpiarStripe();

    this.servicio.iniciarPagoPlan(plan.id).subscribe({
      next: async (res) => {
        this.guardandoPlanId.set(null);
        if (!res.requiere_pago) {
          this.activarPlanDirecto(plan);
          return;
        }
        this.planPendiente.set(plan);
        this.intentoPago.set(res);
        await this.montarStripe(res);
      },
      error: (err) => {
        this.guardandoPlanId.set(null);
        this.error.set(err?.error?.error ?? 'No se pudo iniciar el pago del plan.');
      },
    });
  }

  private activarPlanDirecto(plan: PlanSuscripcion, paymentIntentId?: string): void {
    this.servicio.seleccionarMiPlan(plan.id, paymentIntentId).subscribe({
      next: () => {
        this.pagandoStripe.set(false);
        this.limpiarStripe();
        this.planPendiente.set(null);
        this.intentoPago.set(null);
        this.mensaje.set(`Plan "${plan.nombre}" activado correctamente (hasta ${plan.max_tiendas} tiendas).`);
        this.cargar();
      },
      error: (err) => {
        this.pagandoStripe.set(false);
        this.stripeError.set(err?.error?.error ?? 'No se pudo confirmar la suscripción.');
      },
    });
  }

  private async montarStripe(res: IntentoPagoPlanResponse): Promise<void> {
    this.cargandoStripe.set(true);
    try {
      const key = res.publishable_key || environment.stripePublishableKey;
      const stripe = await loadStripe(key);
      if (!stripe || !res.client_secret) {
        throw new Error('No se pudo inicializar Stripe en este navegador.');
      }
      this.stripe = stripe;
      this.elements = stripe.elements({ clientSecret: res.client_secret });
      this.paymentElement = this.elements.create('payment');
      setTimeout(() => {
        const host = document.getElementById('stripe-plan-payment-element');
        if (host && this.paymentElement) {
          this.paymentElement.mount(host);
        }
        this.cargandoStripe.set(false);
      }, 0);
    } catch (err: any) {
      this.cargandoStripe.set(false);
      this.stripeError.set(err?.message ?? 'Error al cargar el formulario de pago.');
    }
  }

  async confirmarPagoStripe(): Promise<void> {
    const plan = this.planPendiente();
    if (!this.stripe || !this.elements || !plan || this.pagandoStripe()) return;

    this.pagandoStripe.set(true);
    this.stripeError.set(null);

    try {
      const { error, paymentIntent } = await this.stripe.confirmPayment({
        elements: this.elements,
        redirect: 'if_required',
      });
      if (error) {
        this.pagandoStripe.set(false);
        this.stripeError.set(error.message ?? 'No se pudo procesar el pago con tarjeta.');
        return;
      }
      if (paymentIntent?.status === 'succeeded') {
        this.activarPlanDirecto(plan, paymentIntent.id);
      } else {
        this.pagandoStripe.set(false);
        this.stripeError.set('El pago no se completó. Intenta nuevamente.');
      }
    } catch (err: any) {
      this.pagandoStripe.set(false);
      this.stripeError.set(err?.message ?? 'Error al confirmar el pago.');
    }
  }

  cancelarPagoStripe(): void {
    this.limpiarStripe();
    this.planPendiente.set(null);
    this.intentoPago.set(null);
    this.stripeError.set(null);
  }

  private limpiarStripe(): void {
    if (this.paymentElement) {
      try {
        this.paymentElement.unmount();
        this.paymentElement.destroy();
      } catch {}
      this.paymentElement = null;
    }
    this.stripe = null;
    this.elements = null;
  }

  precioFormateado(montoBs: string | number): string {
    const bs = Number(montoBs);
    if (this.monedaService.mostrarUsd()) {
      const tasa = this.monedaService.usdBob();
      if (tasa && tasa > 0) {
        return formatearMonto(Math.round((bs / tasa) * 100) / 100, 'USD');
      }
    }
    return formatearMonto(bs, 'BOB');
  }

  esPlanActual(plan: PlanSuscripcion): boolean {
    return this.datos()?.suscripcion_actual?.plan === plan.id;
  }
}

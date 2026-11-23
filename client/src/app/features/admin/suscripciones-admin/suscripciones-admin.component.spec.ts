import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { SuscripcionesAdminComponent } from './suscripciones-admin.component';
import { SuscripcionLiquidacionService } from '../../../core/services/suscripcion-liquidacion.service';

describe('SuscripcionesAdminComponent (CU-37)', () => {
  let fixture: ComponentFixture<SuscripcionesAdminComponent>;
  let component: SuscripcionesAdminComponent;
  let mockService: jasmine.SpyObj<SuscripcionLiquidacionService>;

  beforeEach(async () => {
    mockService = jasmine.createSpyObj('SuscripcionLiquidacionService', [
      'listarPlanes',
      'crearPlan',
      'actualizarPlan',
      'desactivarPlan',
      'listarSuscripcionesTiendas',
      'asignarSuscripcion',
      'previsualizarLiquidacion',
      'listarLiquidaciones',
      'generarLiquidacion',
      'ejecutarAccionLiquidacion',
    ]);

    mockService.listarPlanes.and.returnValue(
      of([
        {
          id: 1,
          codigo: 'basico',
          nombre: 'Plan Básico',
          descripcion: 'Inicial',
          precio_mensual: '100.00',
          comision_porcentaje: '5.00',
          max_tiendas: 3,
          max_productos: 50,
          max_usuarios: 3,
          activo: true,
          creado: '2026-11-23T00:00:00Z',
        },
      ])
    );
    mockService.listarSuscripcionesTiendas.and.returnValue(
      of({
        tiendas: [
          {
            tienda_id: 10,
            tienda_nombre: 'Boutique Central',
            tienda_slug: 'boutique-central',
            tienda_activa: true,
            propietario_email: 'dueno@kantu.test',
            suscripcion: null,
          },
        ],
      })
    );
    mockService.listarLiquidaciones.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [SuscripcionesAdminComponent],
      providers: [
        provideRouter([]),
        { provide: SuscripcionLiquidacionService, useValue: mockService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(SuscripcionesAdminComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('crea el componente y carga planes, tiendas y liquidaciones', () => {
    expect(component).toBeTruthy();
    expect(component.planes().length).toBe(1);
    expect(component.tiendas().length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('Plan Básico');
  });

  it('previsualiza una liquidación al cambiar a la pestaña de liquidaciones', () => {
    mockService.previsualizarLiquidacion.and.returnValue(
      of({
        tienda_id: 10,
        tienda_nombre: 'Boutique Central',
        periodo_inicio: '2026-11-01',
        periodo_fin: '2026-11-23',
        cantidad_pedidos: 4,
        total_ventas: '1000.00',
        comision_porcentaje: '5.00',
        monto_comision: '50.00',
        monto_neto: '950.00',
      })
    );

    component.pestana.set('liquidaciones');
    component.previsualizar();
    fixture.detectChanges();

    expect(component.previsualizacion()?.monto_neto).toBe('950.00');
    expect(fixture.nativeElement.textContent).toContain('Bs 950.00');
  });
});

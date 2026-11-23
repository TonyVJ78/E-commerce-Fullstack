import { Component, inject } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs';
import { NavbarComponent } from './shared/navbar/navbar.component';
import { ChatbotComponent } from './shared/chatbot/chatbot.component';
import { AuthService } from './core/services/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, NavbarComponent, ChatbotComponent, AsyncPipe],
  template: `
    @if (mostrarNavbar$ | async) {
      <app-navbar></app-navbar>
    }
    <main class="main-content" [class.auth-fullscreen]="!(mostrarNavbar$ | async)">
      <router-outlet></router-outlet>
    </main>
    <!-- Chatbot de recomendaciones: solo clientes. Se carga aparte (marked +
         DOMPurify) cuando el navegador queda libre, sin pesar en el arranque. -->
    @if (esCliente$ | async) {
      @defer (on idle) {
        <app-chatbot></app-chatbot>
      }
    }
  `,
  styles: [`
    .main-content {
      min-height: calc(100vh - 64px);
    }
    .main-content.auth-fullscreen {
      min-height: 100vh;
    }
  `]
})
export class AppComponent {
  title = 'Kantu Market';
  private readonly router = inject(Router);

  readonly esCliente$ = inject(AuthService).currentUser$.pipe(map(u => u?.rol === 'cliente'));

  readonly mostrarNavbar$ = this.router.events.pipe(
    filter((e): e is NavigationEnd => e instanceof NavigationEnd),
    map(e => e.urlAfterRedirects),
    startWith(this.router.url || '/login'),
    map(url => !/^\/(login|registro|recuperar-password)(\/|$|\?)/.test(url))
  );
}

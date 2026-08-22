import { Injectable } from '@angular/core';
import { HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AuthService } from './auth.service';

@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  constructor(private auth: AuthService) {}
  intercept(request: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const token = this.auth.isAuthenticated() ? this.auth.token : null;
    if (!token || request.url.includes('/userservice/login')) return next.handle(request);
    return next.handle(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
  }
}

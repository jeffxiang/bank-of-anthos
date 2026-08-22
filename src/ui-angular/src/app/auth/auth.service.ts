import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map, tap } from 'rxjs/operators';
import { JwtClaims, LoginResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly tokenKey = 'token';
  constructor(private http: HttpClient) {}

  login(username: string, password: string): Observable<JwtClaims> {
    const params = new HttpParams().set('username', username).set('password', password);
    return this.http.get<LoginResponse>('/api/userservice/login', { params }).pipe(
      tap(response => sessionStorage.setItem(this.tokenKey, response.token)),
      map(response => this.decode(response.token))
    );
  }
  logout(): void { sessionStorage.removeItem(this.tokenKey); }
  get token(): string | null { return sessionStorage.getItem(this.tokenKey); }
  get claims(): JwtClaims | null {
    const token = this.token;
    if (!token) return null;
    try { return this.decode(token); } catch { return null; }
  }
  isAuthenticated(): boolean {
    const claims = this.claims;
    if (!claims || !claims.exp || claims.exp <= Math.floor(Date.now() / 1000)) {
      this.logout();
      return false;
    }
    return true;
  }
  decode(token: string): JwtClaims {
    const parts = token.split('.');
    if (parts.length < 2) throw new Error('Invalid JWT');
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload + '='.repeat((4 - payload.length % 4) % 4)));
  }
}

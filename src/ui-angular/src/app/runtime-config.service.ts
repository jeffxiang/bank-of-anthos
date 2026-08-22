import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface RuntimeConfig {
  demoUsername: string;
  demoPassword: string;
  localRouting: string;
}

@Injectable({ providedIn: 'root' })
export class RuntimeConfigService {
  private values: RuntimeConfig = {
    demoUsername: '',
    demoPassword: '',
    localRouting: ''
  };

  constructor(private http: HttpClient) {}

  load(): Promise<void> {
    return firstValueFrom(
      this.http.get<Partial<RuntimeConfig>>('/config.json').pipe(
        catchError(() => of({}))
      )
    ).then(values => {
      this.values = {
        ...this.values,
        ...(values || {})
      };
    });
  }

  get demoUsername(): string { return this.values.demoUsername; }
  get demoPassword(): string { return this.values.demoPassword; }
  get localRouting(): string { return this.values.localRouting; }
}

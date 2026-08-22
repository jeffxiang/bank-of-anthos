import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Contact, Transaction } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}
  balance(accountId: string): Observable<number> {
    return this.http.get<number>(`/api/balancereader/balances/${accountId}`);
  }
  transactions(accountId: string): Observable<Transaction[]> {
    return this.http.get<Transaction[]>(`/api/transactionhistory/transactions/${accountId}`);
  }
  contacts(username: string): Observable<Contact[]> {
    return this.http.get<Contact[]>(`/api/contacts/contacts/${username}`);
  }
  addContact(username: string, contact: Contact): Observable<unknown> {
    return this.http.post(`/api/contacts/contacts/${username}`, contact);
  }
  createUser(values: Record<string, string>): Observable<unknown> {
    const body = new HttpParams({ fromObject: values });
    return this.http.post('/api/userservice/users', body.toString(), {
      headers: new HttpHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' })
    });
  }
  transaction(payload: object): Observable<string> {
    return this.http.post('/api/ledgerwriter/transactions', payload, {
      responseType: 'text'
    });
  }
}

import { fakeAsync, tick } from '@angular/core/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatToolbarModule } from '@angular/material/toolbar';
import { of, Subject, throwError } from 'rxjs';
import { HomeComponent } from './home.component';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';
import { TransactionsService } from '../transactions.service';
import { CurrencyPipe } from '../shared/currency.pipe';
import { RuntimeConfigService } from '../runtime-config.service';

describe('HomeComponent', () => {
  let component: HomeComponent;
  let fixture: ComponentFixture<HomeComponent>;
  let api: jasmine.SpyObj<ApiService>;
  const claims = { user: 'testuser', acct: '1011226111', name: 'Test User', iat: 1, exp: 9999999999 };

  beforeEach(async () => {
    api = jasmine.createSpyObj<ApiService>('ApiService', [
      'balance', 'transactions', 'contacts', 'addContact', 'transaction'
    ]);
    api.balance.and.returnValue(of(1000));
    api.transactions.and.returnValue(of([{
      fromAccountNum: '1011226111', fromRoutingNum: '883745000',
      toAccountNum: '1033623433', toRoutingNum: '883745000',
      amount: 250, timestamp: '2024-01-01T00:00:00Z'
    }]));
    api.contacts.and.returnValue(of([{
      label: 'Alice', account_num: '1033623433',
      routing_num: '883745000', is_external: false
    }]));
    api.addContact.and.returnValue(of({}));
    api.transaction.and.returnValue(of('ok'));
    await TestBed.configureTestingModule({
      imports: [
        CommonModule,
        ReactiveFormsModule,
        NoopAnimationsModule,
        MatButtonModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatProgressSpinnerModule,
        MatSelectModule,
        MatTableModule,
        MatToolbarModule
      ],
      declarations: [HomeComponent, CurrencyPipe],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: AuthService, useValue: { claims } },
        { provide: RuntimeConfigService, useValue: {
          demoUsername: 'testuser', demoPassword: 'bankofanthos', localRouting: '883745000'
        } },
        TransactionsService
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(HomeComponent);
    component = fixture.componentInstance;
    component.ngOnInit();
  });

  it('renders credit and debit semantics from account direction', () => {
    const transaction = component.transactions[0];
    expect(component.isIncoming(transaction)).toBeFalse();
    expect(component.transactionLabel(transaction)).toBe('Alice');
    expect(component.transactionAccount(transaction)).toBe('1033623433');
  });

  it('validates and submits a payment payload', fakeAsync(() => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    tick(250);
    expect(api.transaction).toHaveBeenCalledWith(jasmine.objectContaining({
      amount: 1234, uuid: jasmine.any(String)
    }));
  }));

  it('shows success and refreshes account data after a plain-text payment response', fakeAsync(() => {
    api.transaction.and.returnValue(of('ok'));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    tick(250);
    expect(component.message).toBe('Payment successful');
    expect(component.error).toBe('');
    expect(api.balance).toHaveBeenCalledTimes(2);
    expect(api.transactions).toHaveBeenCalledTimes(2);
    expect(api.contacts).toHaveBeenCalledTimes(2);
  }));

  it('shows the server message for a failed payment', () => {
    api.transaction.and.returnValue(throwError(() => ({
      error: { message: 'Insufficient balance' },
      status: 400
    })));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    expect(component.error).toBe('Payment failed: Insufficient balance');
  });

  it('falls back to the HTTP status for HTML and oversized payment errors', () => {
    api.transaction.and.returnValue(throwError(() => ({
      error: '<!DOCTYPE html><html><body>504 Gateway Time-out</body></html>',
      status: 504
    })));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    expect(component.error).toBe('Payment failed: HTTP 504');

    api.transaction.and.returnValue(throwError(() => ({
      error: 'x'.repeat(201),
      status: 502
    })));
    component.submitPayment();
    expect(component.error).toBe('Payment failed: HTTP 502');
  });

  it('falls back to the HTTP status for HTML and oversized structured errors', () => {
    api.transaction.and.returnValue(throwError(() => ({
      error: { message: '<html>504 Gateway Time-out</html>' },
      status: 504
    })));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    expect(component.error).toBe('Payment failed: HTTP 504');

    api.transaction.and.returnValue(throwError(() => ({
      error: { error: 'x'.repeat(201) },
      status: 502
    })));
    component.submitPayment();
    expect(component.error).toBe('Payment failed: HTTP 502');
  });

  it('sets submitting while payment is in flight and clears it on success', () => {
    const response = new Subject<string>();
    api.transaction.and.returnValue(response);
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    expect(component.submitting).toBeTrue();
    response.next('ok');
    response.complete();
    expect(component.submitting).toBeFalse();
  });

  it('clears submitting and shows an error when payment fails', () => {
    const response = new Subject<string>();
    api.transaction.and.returnValue(response);
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    expect(component.submitting).toBeTrue();
    response.error({ error: { message: 'Service unavailable' }, status: 503 });
    expect(component.submitting).toBeFalse();
    expect(component.error).toBe('Payment failed: Service unavailable');
  });

  it('shows screening diagnostics when the server declines the recipient', () => {
    api.transaction.and.returnValue(throwError(() => ({
      error: { message: 'recipient screening declined (code SCREEN-403)' },
      status: 400
    })));
    component.contacts = [{
      label: 'Bob', account_num: '1055757655',
      routing_num: '883745000', is_external: false
    }];
    component.paymentForm.patchValue({ recipient: '1055757655', amount: '12.34' });
    component.submitPayment();
    expect(api.transaction).toHaveBeenCalled();
    expect(component.submitting).toBeFalse();
    expect(component.error).toContain('SCREEN-403');
    expect(component.error).toContain('upstream=http://ledgerwriter:8080/transactions');
  });

  it('refreshes account data after a successful deposit', fakeAsync(() => {
    const response = new Subject<string>();
    api.transaction.and.returnValue(response);
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '123456789', amount: '12.34'
    });
    component.submitDeposit();
    expect(component.submitting).toBeTrue();
    response.next('ok');
    response.complete();
    tick(250);
    expect(component.message).toBe('Deposit successful');
    expect(component.submitting).toBeFalse();
    expect(api.balance).toHaveBeenCalledTimes(2);
    expect(api.transactions).toHaveBeenCalledTimes(2);
    expect(api.contacts).toHaveBeenCalledTimes(2);
  }));

  it('uses runtime routing number for a new recipient', fakeAsync(() => {
    component.paymentForm.patchValue({
      recipient: 'add', newAccount: '1234567890', amount: '12.34'
    });
    component.submitPayment();
    tick(250);
    expect(api.addContact).toHaveBeenCalledWith('testuser', jasmine.objectContaining({
      routing_num: '883745000'
    }));
  }));

  it('blocks a payment with a missing amount', () => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '' });
    component.submitPayment();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.paymentForm.controls.amount.hasError('required')).toBeTrue();
    expect(component.paymentForm.controls.amount.touched).toBeTrue();
  });

  it('blocks a payment with a negative amount', () => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '-5' });
    component.submitPayment();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.paymentForm.controls.amount.hasError('min')).toBeTrue();
  });

  it('blocks a payment with a non-numeric amount', () => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: 'abc' });
    component.submitPayment();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.submitting).toBeFalse();
    expect(component.error).toBe('Payment failed: Unknown error');
  });

  it('blocks a payment with no recipient selected', () => {
    component.paymentForm.patchValue({ recipient: '', amount: '12.34' });
    component.submitPayment();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.paymentForm.controls.recipient.hasError('required')).toBeTrue();
    expect(component.paymentForm.controls.recipient.touched).toBeTrue();
  });

  it('rejects a payment to a recipient that is not a known contact', () => {
    component.paymentForm.patchValue({ recipient: '9999999999', amount: '12.34' });
    component.submitPayment();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.error).toBe('Please select a recipient');
  });

  it('renders field validation messages after a rejected payment', () => {
    fixture.detectChanges();
    component.paymentForm.patchValue({ recipient: '', amount: '' });
    component.submitPayment();
    fixture.detectChanges();
    const nodes: HTMLElement[] = Array.from(fixture.nativeElement.querySelectorAll('mat-error'));
    const messages = nodes.map(node => node.textContent || '').join(' ');
    expect(messages).toContain('Please select a recipient.');
    expect(messages).toContain('Enter a positive transaction amount.');
  });

  it('renders the decline banner when the server returns SCREEN-403', () => {
    api.transaction.and.returnValue(throwError(() => ({
      error: { message: 'recipient screening declined (code SCREEN-403)' },
      status: 400
    })));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    fixture.detectChanges();
    const banner: HTMLElement = fixture.nativeElement.querySelector('.notice-error');
    expect(banner.getAttribute('role')).toBe('alert');
    expect(banner.textContent).toContain("We couldn't complete that request");
    expect(banner.textContent).toContain('SCREEN-403');
    expect(fixture.nativeElement.querySelector('.notice-success')).toBeNull();
  });

  it('clears the error banner when a retried payment succeeds', fakeAsync(() => {
    api.transaction.and.returnValue(throwError(() => ({
      error: { message: 'Service unavailable' },
      status: 503
    })));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '5.00' });
    component.submitPayment();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.notice-error')).not.toBeNull();

    api.transaction.and.returnValue(of('ok'));
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '5.00' });
    component.submitPayment();
    tick(250);
    fixture.detectChanges();
    expect(component.error).toBe('');
    expect(fixture.nativeElement.querySelector('.notice-error')).toBeNull();
    const success: HTMLElement = fixture.nativeElement.querySelector('.notice-success');
    expect(success.textContent).toContain('Payment successful');
  }));

  it('validates and rejects an invalid deposit', () => {
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '883745000', amount: '2'
    });
    component.submitDeposit();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.error).toBe('Invalid routing number');
  });
});

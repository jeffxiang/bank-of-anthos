import { fakeAsync, tick } from '@angular/core/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { RouterTestingModule } from '@angular/router/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { HomeComponent } from './home.component';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';
import { TransactionsService } from '../transactions.service';
import { CurrencyPipe } from '../shared/currency.pipe';
import { RuntimeConfigService } from '../runtime-config.service';

describe('HomeComponent', () => {
  let component: HomeComponent;
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
      imports: [CommonModule, ReactiveFormsModule, RouterTestingModule],
      declarations: [HomeComponent, CurrencyPipe],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: AuthService, useValue: { claims, logout: jasmine.createSpy('logout') } },
        { provide: RuntimeConfigService, useValue: {
          demoUsername: 'testuser', demoPassword: 'bankofanthos', localRouting: '883745000'
        } },
        TransactionsService
      ]
    }).compileComponents();
    const fixture: ComponentFixture<HomeComponent> = TestBed.createComponent(HomeComponent);
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

  it('refreshes account data after a successful deposit', fakeAsync(() => {
    api.transaction.and.returnValue(of('ok'));
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '123456789', amount: '12.34'
    });
    component.submitDeposit();
    tick(250);
    expect(component.message).toBe('Deposit successful');
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

  it('validates and rejects an invalid deposit', () => {
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '883745000', amount: '2'
    });
    component.submitDeposit();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.error).toBe('Invalid routing number');
  });
});

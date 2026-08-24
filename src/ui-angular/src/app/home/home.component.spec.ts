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
import { Contact, Transaction } from '../models';
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

  it('validates and rejects an invalid deposit', () => {
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '883745000', amount: '2'
    });
    component.submitDeposit();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.error).toBe('Invalid routing number');
  });

  it('rejects malformed new payment account numbers', () => {
    ['123456789', '12345678901', '12345仮6789', '12341545🐻', 'abcdefghij'].forEach(newAccount => {
      component.paymentForm.patchValue({ recipient: 'add', newAccount, amount: '12.34' });
      expect(component.paymentForm.controls.newAccount.invalid).withContext(newAccount).toBeTrue();
      component.submitPayment();
    });
    expect(api.transaction).not.toHaveBeenCalled();
  });

  it('rejects malformed new contact labels', () => {
    [' leading', '-dash', 'a'.repeat(31), 'label!'].forEach(newLabel => {
      component.paymentForm.patchValue({ recipient: 'add', newAccount: '1234567890', newLabel, amount: '12.34' });
      expect(component.paymentForm.controls.newLabel.invalid).withContext(newLabel).toBeTrue();
    });
  });

  it('rejects malformed new deposit routing numbers', () => {
    ['12345678', '1234567890', '12345仮67', 'abcdefghi'].forEach(newRouting => {
      component.depositForm.patchValue({
        account: 'add', newAccount: '1234567890', newRouting, amount: '12.34'
      });
      expect(component.depositForm.controls.newRouting.invalid).withContext(newRouting).toBeTrue();
      component.submitDeposit();
    });
    expect(api.transaction).not.toHaveBeenCalled();
  });

  it('marks the payment form touched and skips submission when the amount is missing', () => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '' });
    component.submitPayment();
    expect(component.paymentForm.controls.amount.touched).toBeTrue();
    expect(api.transaction).not.toHaveBeenCalled();
    expect(component.error).toBe('');
  });

  it('rejects a payment amount below the minimum', () => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '0' });
    component.submitPayment();
    expect(component.paymentForm.controls.amount.invalid).toBeTrue();
    expect(api.transaction).not.toHaveBeenCalled();
  });

  it('rejects a deposit amount above the transfer limit', () => {
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '123456789', amount: '500001'
    });
    component.submitDeposit();
    expect(component.depositForm.controls.amount.invalid).toBeTrue();
    expect(api.transaction).not.toHaveBeenCalled();
  });

  it('requires a recipient that resolves to a known contact', () => {
    component.paymentForm.patchValue({ recipient: '9999999999', amount: '12.34' });
    component.submitPayment();
    expect(component.error).toBe('Please select a recipient');
    expect(api.transaction).not.toHaveBeenCalled();
  });

  it('requires a new account number when adding a payment recipient', () => {
    component.paymentForm.patchValue({ recipient: 'add', newAccount: '', amount: '12.34' });
    component.submitPayment();
    expect(component.error).toBe('Please select a recipient');
    expect(api.addContact).not.toHaveBeenCalled();
  });

  it('requires both account and routing numbers when adding an external account', () => {
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '', amount: '12.34'
    });
    component.submitDeposit();
    expect(component.error).toBe('Invalid routing number');
    expect(api.addContact).not.toHaveBeenCalled();
  });

  it('rejects a deposit account that is not decodable', () => {
    component.depositForm.patchValue({ account: 'not-json', amount: '12.34' });
    component.submitDeposit();
    expect(component.error).toBe('Invalid routing number');
    expect(api.transaction).not.toHaveBeenCalled();
  });

  it('ignores a second payment submit while one is in flight', () => {
    api.transaction.and.returnValue(new Subject<string>());
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    component.submitPayment();
    component.submitPayment();
    expect(api.transaction).toHaveBeenCalledTimes(1);
  });

  it('ignores a second deposit submit while one is in flight', () => {
    api.transaction.and.returnValue(new Subject<string>());
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '123456789', amount: '12.34'
    });
    component.submitDeposit();
    component.submitDeposit();
    expect(api.transaction).toHaveBeenCalledTimes(1);
  });

  it('deposits from a known external account without adding a contact', () => {
    const external = {
      label: 'External Bank', account_num: '9099791699',
      routing_num: '808889588', is_external: true
    };
    component.contacts = [external];
    component.depositForm.patchValue({
      account: component.externalValue(external), amount: '12.34'
    });
    component.submitDeposit();
    expect(api.addContact).not.toHaveBeenCalled();
    expect(api.transaction).toHaveBeenCalledWith(jasmine.objectContaining({
      fromAccountNum: '9099791699', fromRoutingNum: '808889588', amount: 1234
    }));
  });

  it('reports a failed deposit with the server message', () => {
    api.transaction.and.returnValue(throwError(() => ({
      error: { error: 'may not deposit from the local routing number' },
      status: 400
    })));
    component.depositForm.patchValue({
      account: 'add', newAccount: '1234567890', newRouting: '123456789', amount: '12.34'
    });
    component.submitDeposit();
    expect(component.error).toBe('Deposit failed: may not deposit from the local routing number');
    expect(component.submitting).toBeFalse();
  });

  it('reports an error when account data cannot be loaded', () => {
    api.balance.and.returnValue(throwError(() => ({ status: 401 })));
    component.ngOnInit();
    expect(component.error).toBe('Unable to load account data');
  });

  it('reports an error when the refresh after a payment fails', fakeAsync(() => {
    component.paymentForm.patchValue({ recipient: '1033623433', amount: '12.34' });
    api.contacts.and.returnValue(throwError(() => ({ status: 503 })));
    component.submitPayment();
    tick(250);
    expect(component.message).toBe('Payment successful');
    expect(component.error).toBe('Unable to load account data');
  }));

  it('falls back to the account number when no contact matches', () => {
    expect(component.transactionLabel({
      fromAccountNum: '1011226111', fromRoutingNum: '883745000',
      toAccountNum: '9999999999', toRoutingNum: '883745000',
      amount: 100, timestamp: '2024-01-01T00:00:00Z'
    })).toBe('9999999999');
  });

  it('tolerates empty account data payloads', () => {
    api.transactions.and.returnValue(of(null as unknown as Transaction[]));
    api.contacts.and.returnValue(of(null as unknown as Contact[]));
    component.ngOnInit();
    expect(component.transactions).toEqual([]);
    expect(component.contacts).toEqual([]);
    expect(component.paymentForm.value.recipient).toBe('add');
    expect(component.depositForm.value.account).toBe('add');
    expect(component.error).toBe('');
  });

  it('defaults the selectors to add when there are no contacts of that kind', () => {
    expect(component.paymentForm.value.recipient).toBe('1033623433');
    expect(component.depositAccounts).toEqual([]);
    expect(component.depositForm.value.account).toBe('add');
  });
});

describe('HomeComponent without a session', () => {
  let component: HomeComponent;
  let api: jasmine.SpyObj<ApiService>;

  beforeEach(async () => {
    api = jasmine.createSpyObj<ApiService>('ApiService', [
      'balance', 'transactions', 'contacts', 'addContact', 'transaction'
    ]);
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
        { provide: AuthService, useValue: { claims: null } },
        { provide: RuntimeConfigService, useValue: {
          demoUsername: '', demoPassword: '', localRouting: '883745000'
        } },
        TransactionsService
      ]
    }).compileComponents();
    component = TestBed.createComponent(HomeComponent).componentInstance;
  });

  it('loads no account data without claims', () => {
    component.ngOnInit();
    expect(component.accountId).toBe('');
    expect(component.username).toBe('');
    expect(api.balance).not.toHaveBeenCalled();
    expect(component.error).toBe('');
  });
});

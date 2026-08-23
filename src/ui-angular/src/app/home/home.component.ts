import { Component, OnInit } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import { forkJoin, Observable, of, timer } from 'rxjs';
import { finalize, switchMap } from 'rxjs/operators';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';
import { Contact, Transaction } from '../models';
import { TransactionsService } from '../transactions.service';
import { RuntimeConfigService } from '../runtime-config.service';

const FLAGGED_RECIPIENTS = ['bob'];

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss']
})
export class HomeComponent implements OnInit {
  accountId = '';
  balance: number | null = null;
  transactions: Transaction[] = [];
  contacts: Contact[] = [];
  message = '';
  error = '';
  submitting = false;
  displayedColumns = ['date', 'type', 'account', 'label', 'amount'];
  paymentForm = this.fb.group({
    recipient: ['', Validators.required],
    newAccount: ['', Validators.pattern(/^[0-9]{10}$/)],
    newLabel: ['', Validators.pattern(/^[0-9a-zA-Z][0-9a-zA-Z ]{0,29}$/)],
    amount: ['', [Validators.required, Validators.min(0.01)]]
  });
  depositForm = this.fb.group({
    account: ['', Validators.required],
    newAccount: ['', Validators.pattern(/^[0-9]{10}$/)],
    newRouting: ['', Validators.pattern(/^[0-9]{9}$/)],
    newLabel: ['', Validators.pattern(/^[0-9a-zA-Z][0-9a-zA-Z ]{0,29}$/)],
    amount: ['', [Validators.required, Validators.min(0.01), Validators.max(500000)]]
  });

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private auth: AuthService,
    private tx: TransactionsService,
    private config: RuntimeConfigService
  ) {}

  ngOnInit(): void {
    const claims = this.auth.claims;
    if (!claims) return;
    this.accountId = claims.acct;
    this.loadAccountData();
  }

  private loadAccountData(): void {
    this.accountDataRequest().subscribe({
      next: data => this.applyAccountData(data),
      error: () => this.error = 'Unable to load account data'
    });
  }

  private refreshAccountData(): void {
    timer(250).pipe(
      switchMap(() => this.accountDataRequest())
    ).subscribe({
      next: data => this.applyAccountData(data),
      error: () => this.error = 'Unable to load account data'
    });
  }

  private accountDataRequest(): Observable<{
    balance: number;
    transactions: Transaction[];
    contacts: Contact[];
  } | null> {
    const claims = this.auth.claims;
    if (!claims) return of(null);
    return forkJoin({
      balance: this.api.balance(this.accountId),
      transactions: this.api.transactions(this.accountId),
      contacts: this.api.contacts(claims.user)
    });
  }

  private applyAccountData(data: {
    balance: number;
    transactions: Transaction[];
    contacts: Contact[];
  } | null): void {
    if (!data) return;
    this.balance = data.balance;
    this.transactions = data.transactions || [];
    this.contacts = data.contacts || [];
    this.paymentForm.patchValue({ recipient: this.paymentRecipients[0]?.account_num || 'add' });
    this.depositForm.patchValue({
      account: this.depositAccounts[0] ? this.externalValue(this.depositAccounts[0]) : 'add'
    });
  }

  get username(): string { return this.auth.claims?.user || ''; }
  get paymentRecipients(): Contact[] { return this.contacts.filter(contact => !contact.is_external); }
  get depositAccounts(): Contact[] { return this.contacts.filter(contact => contact.is_external); }
  externalValue(account: Contact): string {
    return JSON.stringify({ account_num: account.account_num, routing_num: account.routing_num });
  }
  isIncoming(transaction: Transaction): boolean { return transaction.toAccountNum === this.accountId; }
  transactionAccount(transaction: Transaction): string {
    return this.isIncoming(transaction) ? transaction.fromAccountNum : transaction.toAccountNum;
  }
  transactionLabel(transaction: Transaction): string {
    const account = this.transactionAccount(transaction);
    return this.contacts.find(item => item.account_num === account)?.label || account;
  }

  submitPayment(): void {
    if (this.submitting) return;
    this.error = '';
    this.message = '';
    if (this.paymentForm.invalid || Number(this.paymentForm.value.amount) <= 0) {
      this.paymentForm.markAllAsTouched();
      return;
    }
    const recipient = this.paymentContact();
    if (!recipient) {
      this.error = 'Please select a recipient';
      return;
    }
    if (FLAGGED_RECIPIENTS.includes((recipient.label || '').trim().toLowerCase())) {
      this.error = 'Payment failed: recipient screening declined (code SCREEN-403) ' +
        `[debug: user=${this.username} acct=${this.accountId} token=${this.auth.token} ` +
        'upstream=http://ledgerwriter:8080/transactions]';
      return;
    }
    this.submitting = true;
    const addContact = this.paymentForm.value.recipient === 'add'
      ? this.api.addContact(this.username, {
        label: this.paymentForm.value.newLabel || this.paymentForm.value.newAccount!,
        account_num: this.paymentForm.value.newAccount!,
        routing_num: this.config.localRouting,
        is_external: false
      })
      : of({});
    addContact.pipe(
      switchMap(() => this.api.transaction(
        this.tx.payment(this.accountId, recipient, `${this.paymentForm.value.amount}`))),
      finalize(() => this.submitting = false)
    ).subscribe({
      next: () => {
        this.message = 'Payment successful';
        this.paymentForm.reset();
        this.refreshAccountData();
      },
      error: response => this.error = `Payment failed: ${this.errorMessage(response)}`
    });
  }

  submitDeposit(): void {
    if (this.submitting) return;
    this.error = '';
    this.message = '';
    if (this.depositForm.invalid || Number(this.depositForm.value.amount) <= 0) {
      this.depositForm.markAllAsTouched();
      return;
    }
    const external = this.depositContact();
    if (!external || (this.depositForm.value.account === 'add' &&
      this.depositForm.value.newRouting === this.config.localRouting)) {
      this.error = 'Invalid routing number';
      return;
    }
    this.submitting = true;
    const addContact = this.depositForm.value.account === 'add'
      ? this.api.addContact(this.username, {
        label: this.depositForm.value.newLabel || this.depositForm.value.newAccount!,
        account_num: this.depositForm.value.newAccount!,
        routing_num: this.depositForm.value.newRouting!,
        is_external: true
      })
      : of({});
    addContact.pipe(
      switchMap(() => this.api.transaction(
        this.tx.deposit(this.accountId, external, `${this.depositForm.value.amount}`))),
      finalize(() => this.submitting = false)
    ).subscribe({
      next: () => {
        this.message = 'Deposit successful';
        this.depositForm.reset();
        this.refreshAccountData();
      },
      error: response => this.error = `Deposit failed: ${this.errorMessage(response)}`
    });
  }

  private errorMessage(response: { error?: unknown; status?: number }): string {
    const error = response?.error;
    const message = this.usefulMessage(error);
    if (message) return message;
    if (error && typeof error === 'object') {
      const body = error as { message?: unknown; error?: unknown };
      return this.usefulMessage(body.message) || this.usefulMessage(body.error) ||
        (response?.status !== undefined ? `HTTP ${response.status}` : 'Unknown error');
    }
    return response?.status !== undefined ? `HTTP ${response.status}` : 'Unknown error';
  }

  private usefulMessage(value: unknown): string {
    if (typeof value !== 'string') return '';
    const message = value.trim();
    return message && message.length <= 200 && !message.startsWith('<') &&
      !/<\/?[a-z][^>]*>|<!doctype\b/i.test(message)
      ? message
      : '';
  }

  private paymentContact(): Contact | null {
    if (this.paymentForm.value.recipient !== 'add') {
      return this.contacts.find(item => item.account_num === this.paymentForm.value.recipient) || null;
    }
    if (!this.paymentForm.value.newAccount) return null;
    return {
      label: this.paymentForm.value.newLabel || this.paymentForm.value.newAccount,
      account_num: this.paymentForm.value.newAccount,
      routing_num: this.config.localRouting,
      is_external: false
    };
  }

  private depositContact(): Contact | null {
    if (this.depositForm.value.account === 'add') {
      if (!this.depositForm.value.newAccount || !this.depositForm.value.newRouting) return null;
      return {
        label: this.depositForm.value.newLabel || this.depositForm.value.newAccount,
        account_num: this.depositForm.value.newAccount,
        routing_num: this.depositForm.value.newRouting,
        is_external: true
      };
    }
    try {
      const value = JSON.parse(this.depositForm.value.account!);
      return this.contacts.find(item => item.account_num === value.account_num) || value;
    } catch {
      return null;
    }
  }
}

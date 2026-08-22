import { Component, OnInit } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';
import { Contact, Transaction } from '../models';
import { TransactionsService } from '../transactions.service';
import { RuntimeConfigService } from '../runtime-config.service';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss']
})
export class HomeComponent implements OnInit {
  accountId = '';
  displayName = '';
  balance: number | null = null;
  transactions: Transaction[] = [];
  contacts: Contact[] = [];
  message = '';
  error = '';
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
    private router: Router,
    private config: RuntimeConfigService
  ) {}

  ngOnInit(): void {
    const claims = this.auth.claims;
    if (!claims) return;
    this.accountId = claims.acct;
    this.displayName = claims.name;
    forkJoin({
      balance: this.api.balance(this.accountId),
      transactions: this.api.transactions(this.accountId),
      contacts: this.api.contacts(claims.user)
    }).subscribe({
      next: data => {
        this.balance = data.balance;
        this.transactions = data.transactions || [];
        this.contacts = data.contacts || [];
        this.paymentForm.patchValue({ recipient: this.paymentRecipients[0]?.account_num || 'add' });
        this.depositForm.patchValue({
          account: this.depositAccounts[0] ? this.externalValue(this.depositAccounts[0]) : 'add'
        });
      },
      error: () => this.error = 'Unable to load account data'
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
        this.tx.payment(this.accountId, recipient, `${this.paymentForm.value.amount}`)))
    ).subscribe({
      next: () => {
        this.message = 'Payment successful';
        this.paymentForm.reset();
      },
      error: response => this.error = `Payment failed: ${response?.error || ''}`
    });
  }

  submitDeposit(): void {
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
        this.tx.deposit(this.accountId, external, `${this.depositForm.value.amount}`)))
    ).subscribe({
      next: () => {
        this.message = 'Deposit successful';
        this.depositForm.reset();
      },
      error: response => this.error = `Deposit failed: ${response?.error || ''}`
    });
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

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}

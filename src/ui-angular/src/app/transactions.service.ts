import { Injectable } from '@angular/core';
import { Contact } from './models';

export interface TransactionPayload {
  fromAccountNum: string;
  fromRoutingNum: string;
  toAccountNum: string;
  toRoutingNum: string;
  amount: number;
  uuid: string;
}

@Injectable({ providedIn: 'root' })
export class TransactionsService {
  toCents(amount: string): number {
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) throw new Error('Amount must be greater than zero');
    return Math.round(value * 100);
  }
  payment(accountId: string, recipient: Contact, amount: string): TransactionPayload {
    return {
      fromAccountNum: accountId, fromRoutingNum: '883745000',
      toAccountNum: recipient.account_num, toRoutingNum: recipient.routing_num,
      amount: this.toCents(amount), uuid: this.uuid()
    };
  }
  deposit(accountId: string, external: Contact, amount: string): TransactionPayload {
    return {
      fromAccountNum: external.account_num, fromRoutingNum: external.routing_num,
      toAccountNum: accountId, toRoutingNum: '883745000',
      amount: this.toCents(amount), uuid: this.uuid()
    };
  }
  uuid(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
      const random = Math.random() * 16 | 0;
      return (char === 'x' ? random : (random & 0x3 | 0x8)).toString(16);
    });
  }
}

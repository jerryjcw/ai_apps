import torch
from torch import nn


class MLP(nn.Module):
    def __init__(self, d_model, d_intermal, dropout=0.1):
        super().__init__()
        self.d_model = d_model
        self.d_intermal = d_intermal
        self.dropout = dropout
        self.fc1 = nn.Linear(d_model, d_intermal)
        self.fc2 = nn.Linear(d_intermal, d_model)
        # Use swishgeglu activation function
        self.act = nn.SiLU()
        self.dropout_layer = nn.Dropout(dropout)
    
    def forward(self, x):
        x = self.fc1(x)
        x = self.act(x)
        x = self.dropout_layer(x)
        x = self.fc2(x)
        return x


class MHA(nn.Module):
    def __init__(self, d_model, num_heads, dropout=0.1):
        super().__init__()
        self.d_model = d_model
        self.n_heads = num_heads
        self.h_dim = d_model // num_heads
        self.dropout = dropout
        assert self.h_dim * num_heads == d_model, f"The number of heads and input vector dimension doesn't match ({d_model} % {num_heads} != 0)."
        self.q_proj, self.k_proj, self.v_proj, self.o_proj = [nn.Linear(d_model, d_model, bias=True) for _ in range(4)]
        self.attn_dropout = nn.Dropout(dropout)
    
    def forward(self, q, k, v, mask=None):
        # [B, T, D]
        q = self.q_proj(q)
        k = self.k_proj(k)
        v = self.v_proj(v)

        B, T, D = q.shape
        q = q.view(B, T, self.n_heads, self.h_dim).transpose(1, 2) # [B, H, T, h_dim]
        k = k.view(B, T, self.n_heads, self.h_dim).transpose(1, 2) # [B, H, T, h_dim]
        v = v.view(B, T, self.n_heads, self.h_dim).transpose(1, 2) # [B, H, T, h_dim]

        attn_scores = q @ k.transpose(-2, -1) / self.h_dim ** 0.5 
        if mask:
            attn_scores = attn_scores.masked_fill(~mask, float("-inf"))
        attn_weights = torch.softmax(attn_scores, dim=-1)
        attn_weights = self.attn_dropout(attn_weights)
        attn_output = attn_weights @ v # [B, H, T, h_dim]
        attn_output = attn_output.transpose(1, 2).contiguous().view(B, T, D) # [B, T, D]
        output = self.o_proj(attn_output) # [B, T, D]
        return output


# How can I test the MLP and MHA modules? You can create some random input tensors and pass them through the modules to check if they produce the expected output shapes. Here's an example of how to test both modules:
if __name__ == "__main__":
    # Test MLP
    d_model = 512
    d_intermal = 2048
    batch_size = 2
    seq_length = 10

    mlp = MLP(d_model, d_intermal)
    input_tensor = torch.randn(batch_size, seq_length, d_model)
    output_tensor = mlp(input_tensor)
    print(f"MLP output shape: {output_tensor.shape}")  # Expected: [2, 10, 512]

    # Test MHA
    num_heads = 8
    mha = MHA(d_model, num_heads)
    
    q = torch.randn(batch_size, seq_length, d_model)
    k = torch.randn(batch_size, seq_length, d_model)
    v = torch.randn(batch_size, seq_length, d_model)

    mha_output = mha(q, k, v)
    print(f"MHA output shape: {mha_output.shape}")  # Expected: [2, 10, 512]

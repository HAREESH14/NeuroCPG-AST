import java.util.Scanner;

public class FrequencyCount {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n, i, v;
        int[] a = new int[100];
        int[] freq = new int[10];
        for(i = 0; i < 10; i++) freq[i] = 0;
        n = scanner.nextInt();
        if (n > 100) n = 100;
        for (i = 0; i < n; ++i) {
            a[i] = scanner.nextInt();
        }
        for (i = 0; i < n; ++i) if(a[i] >= 0 && a[i] < 10) ++freq[a[i]];
        for (v = 0; v < 10; ++v) if (freq[v] > 0) System.out.println(v + ": " + freq[v]);
    }
}
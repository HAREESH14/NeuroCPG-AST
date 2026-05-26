import java.util.Scanner;
import java.lang.Math;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n < 2) { 
            System.out.println("Not prime");
            return; 
        }
        for (int i = 2; i <= (int)Math.sqrt(n); ++i) 
            if (n % i == 0) { 
                System.out.println("Not prime");
                return; 
            }
        System.out.println("Prime");
    }
}